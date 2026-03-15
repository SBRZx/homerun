#!/usr/bin/env python3
"""
Video Transcript Extractor for Bookmarks

Usage:
    python extract-transcripts.py <bookmarks.json> [obsidian-vault-dir]

Scans the bookmark JSON for video bookmarks, downloads videos via yt-dlp,
transcribes them with OpenAI Whisper, and appends transcripts to the
corresponding Obsidian markdown files (if vault dir is provided).

Requirements:
    pip install yt-dlp openai-whisper

Optional (faster, requires API key):
    pip install openai
    export OPENAI_API_KEY=sk-...
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def find_video_bookmarks(bookmarks: list[dict]) -> list[dict]:
    """Return bookmarks that contain video media."""
    videos = []
    for bm in bookmarks:
        media = bm.get("tweet_media") or []
        if isinstance(media, dict):
            media = [media]
        for m in media:
            if not isinstance(m, dict):
                continue
            if m.get("type") == "video" or m.get("video_url") or m.get("video_src"):
                videos.append(bm)
                break
    return videos


def get_video_url(bm: dict) -> str:
    """Extract the best video URL from a bookmark."""
    media = bm.get("tweet_media") or []
    if isinstance(media, dict):
        media = [media]

    for m in media:
        if not isinstance(m, dict):
            continue
        # Prefer direct video URL
        if m.get("video_url"):
            return m["video_url"]
        # Try video_src array (pick highest quality = last)
        src = m.get("video_src") or []
        if isinstance(src, list) and src:
            return src[-1]

    # Fallback: use tweet URL (yt-dlp can handle x.com/twitter.com links)
    return bm.get("tweet_url") or ""


def download_video(url: str, output_path: str) -> bool:
    """Download video using yt-dlp."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--format", "bestaudio/best",
                "--extract-audio",
                "--audio-format", "wav",
                "--output", output_path,
                "--quiet",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("  ERROR: yt-dlp not found. Install with: pip install yt-dlp")
        return False
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT downloading {url}")
        return False


def transcribe_whisper_local(audio_path: str) -> str:
    """Transcribe using local whisper model."""
    try:
        import whisper
    except ImportError:
        print("  ERROR: whisper not found. Install with: pip install openai-whisper")
        return ""

    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    return result.get("text", "")


def transcribe_whisper_api(audio_path: str) -> str:
    """Transcribe using OpenAI Whisper API (faster, requires API key)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        return result.text
    except ImportError:
        return ""
    except Exception as e:
        print(f"  API transcription failed: {e}")
        return ""


def transcribe(audio_path: str) -> str:
    """Try API first, fall back to local whisper."""
    text = transcribe_whisper_api(audio_path)
    if text:
        return text
    return transcribe_whisper_local(audio_path)


def safe_filename(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] if text else "untitled"


def find_md_file(vault_dir: Path, bm: dict) -> Path | None:
    """Try to find the markdown file for a bookmark in the vault."""
    posted_by = str(bm.get("posted_by") or bm.get("posted_by_nickname") or "unknown")
    tweet_date = str(bm.get("tweet_date") or "")
    date_prefix = ""
    if tweet_date:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(tweet_date.replace("Z", "+00:00"))
            date_prefix = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_prefix = tweet_date[:10] if len(tweet_date) >= 10 else ""

    # Search for matching file
    pattern = f"{date_prefix}*{posted_by}*"
    matches = list(vault_dir.rglob(pattern + ".md"))
    if matches:
        return matches[0]

    # Broader search by bookmark ID
    bm_id = str(bm.get("id") or "")
    if bm_id:
        matches = list(vault_dir.rglob(f"*{bm_id}*.md"))
        if matches:
            return matches[0]

    return None


def append_transcript(md_path: Path, transcript: str) -> None:
    """Append transcript section to an existing markdown file."""
    content = md_path.read_text(encoding="utf-8")
    if "## Transcript" in content:
        return  # Already has transcript

    content += "\n## Transcript\n\n" + transcript.strip() + "\n"
    md_path.write_text(content, encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract-transcripts.py <bookmarks.json> [obsidian-vault-dir]")
        print("\n  Extracts transcripts from video bookmarks.")
        print("  If vault dir is provided, appends transcripts to markdown files.")
        sys.exit(1)

    json_path = sys.argv[1]
    vault_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"Reading {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    if isinstance(bookmarks, dict):
        bookmarks = list(bookmarks.values())

    video_bookmarks = find_video_bookmarks(bookmarks)
    print(f"Found {len(video_bookmarks)} video bookmarks out of {len(bookmarks)} total.\n")

    if not video_bookmarks:
        print("No video bookmarks to process.")
        return

    transcripts = []
    failed = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, bm in enumerate(video_bookmarks):
            bm_id = bm.get("id") or str(i)
            url = get_video_url(bm)
            posted_by = bm.get("posted_by") or "unknown"

            print(f"[{i + 1}/{len(video_bookmarks)}] {posted_by}: {url[:80]}...")

            if not url:
                print("  SKIP: no video URL found")
                failed.append(bm_id)
                continue

            audio_path = os.path.join(tmp_dir, f"{bm_id}.wav")

            # Download
            if not download_video(url, audio_path):
                # Try tweet URL as fallback
                tweet_url = bm.get("tweet_url") or ""
                if tweet_url and tweet_url != url:
                    print(f"  Retrying with tweet URL: {tweet_url[:80]}...")
                    if not download_video(tweet_url, audio_path):
                        print("  FAILED to download")
                        failed.append(bm_id)
                        continue
                else:
                    print("  FAILED to download")
                    failed.append(bm_id)
                    continue

            # Transcribe
            text = transcribe(audio_path)
            if not text:
                print("  FAILED to transcribe")
                failed.append(bm_id)
                continue

            print(f"  OK: {len(text)} chars")
            transcripts.append({
                "id": bm_id,
                "url": url,
                "posted_by": posted_by,
                "transcript": text,
            })

            # Append to markdown if vault provided
            if vault_dir and vault_dir.exists():
                md_file = find_md_file(vault_dir, bm)
                if md_file:
                    append_transcript(md_file, text)
                    print(f"  Appended to {md_file.name}")

            # Clean up audio
            try:
                os.remove(audio_path)
            except OSError:
                pass

    # Save transcripts JSON
    output_path = json_path.replace(".json", "-transcripts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcripts, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(transcripts)} transcripts extracted, {len(failed)} failed.")
    print(f"Transcripts saved to {output_path}")
    if vault_dir:
        print(f"Markdown files updated in {vault_dir}")


if __name__ == "__main__":
    main()

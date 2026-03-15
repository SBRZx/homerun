#!/usr/bin/env python3
"""
Obsidian Vault Enricher — Fetches linked content and transcribes videos

Usage:
    pip install trafilatura yt-dlp openai-whisper
    python enrich-vault.py ./obsidian-vault/

Walks through all markdown files in the vault and:
1. Fetches linked articles/blogs and embeds readable text
2. Downloads videos and transcribes them with Whisper
3. Adds image descriptions where possible
4. Marks each file as enriched so it won't be re-processed

Requirements:
    pip install trafilatura          # article extraction
    pip install yt-dlp               # video download
    pip install openai-whisper       # local transcription (free)
    # OR
    pip install openai               # OpenAI API transcription (faster, paid)
    export OPENAI_API_KEY=sk-...
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Article extraction
# ---------------------------------------------------------------------------

def fetch_article(url: str) -> dict:
    """Fetch a URL and extract readable article content."""
    try:
        import trafilatura
    except ImportError:
        print("    SKIP article fetch (install trafilatura: pip install trafilatura)")
        return {}

    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True)
        if not downloaded:
            return {}

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_links=True,
            output_format="txt",
        )

        metadata = trafilatura.extract(
            downloaded,
            include_comments=False,
            output_format="xmltei",
            with_metadata=True,
        )

        # Extract metadata
        title = ""
        author = ""
        date = ""
        try:
            meta = trafilatura.metadata.extract_metadata(downloaded)
            if meta:
                title = meta.title or ""
                author = meta.author or ""
                date = meta.date or ""
        except Exception:
            pass

        return {
            "title": title,
            "author": author,
            "date": date,
            "text": text or "",
            "url": url,
        }
    except Exception as e:
        print(f"    ERROR fetching {url}: {e}")
        return {}


def is_article_url(url: str) -> bool:
    """Check if a URL is likely an article (not an image, video, social profile)."""
    if not url:
        return False

    skip_domains = {
        "x.com", "twitter.com", "instagram.com", "facebook.com",
        "tiktok.com", "youtube.com", "youtu.be", "t.co",
        "pbs.twimg.com", "abs.twimg.com", "video.twimg.com",
        "pic.twitter.com",
    }

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        if domain in skip_domains:
            return False

        # Skip direct media files
        path = parsed.path.lower()
        media_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".svg"}
        if any(path.endswith(ext) for ext in media_exts):
            return False

        return True
    except Exception:
        return False


def is_video_url(url: str) -> bool:
    """Check if a URL is likely a video."""
    if not url:
        return False
    video_indicators = [
        "youtube.com/watch", "youtu.be/", "vimeo.com/",
        "video.twimg.com", ".mp4", "tiktok.com",
        "x.com/i/status", "twitter.com/i/status",
    ]
    return any(ind in url.lower() for ind in video_indicators)


# ---------------------------------------------------------------------------
# Video transcription
# ---------------------------------------------------------------------------

def download_audio(url: str, output_path: str) -> bool:
    """Download audio from a video URL using yt-dlp."""
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
                "--no-warnings",
            ] + [url],
            capture_output=True,
            text=True,
            timeout=180,
        )
        # yt-dlp may add .wav extension
        if not os.path.exists(output_path):
            wav_path = output_path + ".wav"
            if os.path.exists(wav_path):
                os.rename(wav_path, output_path)
        return os.path.exists(output_path)
    except FileNotFoundError:
        print("    SKIP video (install yt-dlp: pip install yt-dlp)")
        return False
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT downloading {url}")
        return False
    except Exception as e:
        print(f"    ERROR downloading: {e}")
        return False


def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file. Tries OpenAI API first, falls back to local whisper."""
    # Try OpenAI API
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(model="whisper-1", file=f)
            return result.text
        except Exception as e:
            print(f"    API transcription failed: {e}, trying local...")

    # Fall back to local whisper
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return result.get("text", "")
    except ImportError:
        print("    SKIP transcription (install: pip install openai-whisper)")
        return ""
    except Exception as e:
        print(f"    Transcription error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Markdown parsing and updating
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple:
    """Split markdown into frontmatter dict and body."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    return parts[1], parts[2]


def extract_urls_from_md(content: str) -> list:
    """Extract all URLs from markdown content."""
    # Match markdown links [text](url) and bare URLs
    md_links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', content)
    urls = [url for _, url in md_links]

    # Also find bare URLs
    bare_urls = re.findall(r'https?://[^\s\)>\]]+', content)
    urls.extend(bare_urls)

    return list(set(urls))


def already_enriched(content: str) -> bool:
    """Check if file has already been enriched."""
    return "<!-- enriched -->" in content


def enrich_file(md_path: Path, tmp_dir: str, stats: dict) -> None:
    """Enrich a single markdown file with fetched content."""
    content = md_path.read_text(encoding="utf-8")

    if already_enriched(content):
        stats["skipped"] += 1
        return

    urls = extract_urls_from_md(content)
    if not urls:
        stats["no_urls"] += 1
        return

    additions = []

    # --- Fetch articles ---
    article_urls = [u for u in urls if is_article_url(u)]
    for url in article_urls[:3]:  # limit to 3 articles per bookmark
        print(f"    Fetching article: {url[:80]}...")
        article = fetch_article(url)
        if article and article.get("text"):
            text = article["text"].strip()
            if len(text) > 100:  # only include substantial content
                title = article.get("title") or url
                author = article.get("author") or ""
                header = f"### {title}"
                if author:
                    header += f" — {author}"

                additions.append(
                    f"\n## Article: {title}\n\n"
                    f"*Source: [{url}]({url})*\n\n"
                    + (f"*Author: {author}*\n\n" if author else "")
                    + text + "\n"
                )
                stats["articles"] += 1
                time.sleep(1)  # rate limit

    # --- Transcribe videos ---
    video_urls = [u for u in urls if is_video_url(u)]
    # Also check tweet URL itself for video posts
    if any("video" in content.lower() for _ in [1]):
        source_match = re.search(r'source: "([^"]*)"', content)
        if source_match:
            tweet_url = source_match.group(1)
            if tweet_url and tweet_url not in video_urls:
                video_urls.append(tweet_url)

    for url in video_urls[:2]:  # limit to 2 videos per bookmark
        print(f"    Transcribing video: {url[:80]}...")
        audio_path = os.path.join(tmp_dir, f"audio_{hash(url)}.wav")
        if download_audio(url, audio_path):
            transcript = transcribe_audio(audio_path)
            if transcript:
                additions.append(
                    f"\n## Video Transcript\n\n"
                    f"*Source: [{url}]({url})*\n\n"
                    + transcript.strip() + "\n"
                )
                stats["transcripts"] += 1
            try:
                os.remove(audio_path)
            except OSError:
                pass

    if additions:
        # Add enriched content before the Links section, or at the end
        enriched_content = "\n".join(additions)
        marker = "<!-- enriched -->\n"

        if "## Links" in content:
            content = content.replace("## Links", enriched_content + "\n## Links")
        elif "## Notes" in content:
            content = content.replace("## Notes", enriched_content + "\n## Notes")
        else:
            content += "\n" + enriched_content

        content += "\n" + marker
        md_path.write_text(content, encoding="utf-8")
        stats["enriched"] += 1
    else:
        # Mark as processed even if nothing was added, to avoid re-processing
        content += "\n<!-- enriched -->\n"
        md_path.write_text(content, encoding="utf-8")
        stats["no_content"] += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python enrich-vault.py <obsidian-vault-dir> [--articles-only] [--videos-only]")
        print("\nEnriches Obsidian bookmark files with fetched article text and video transcripts.")
        print("\nRequirements:")
        print("  pip install trafilatura     # for article extraction")
        print("  pip install yt-dlp          # for video download")
        print("  pip install openai-whisper  # for transcription (or set OPENAI_API_KEY)")
        sys.exit(1)

    vault_dir = Path(sys.argv[1])
    if not vault_dir.exists():
        print(f"ERROR: {vault_dir} does not exist")
        sys.exit(1)

    # Find all markdown files (skip MOC files)
    md_files = [f for f in vault_dir.rglob("*.md") if not f.name.startswith("_MOC")]
    print(f"Found {len(md_files)} bookmark files in {vault_dir}\n")

    stats = {
        "enriched": 0,
        "articles": 0,
        "transcripts": 0,
        "skipped": 0,
        "no_urls": 0,
        "no_content": 0,
        "errors": 0,
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, md_file in enumerate(md_files):
            rel = md_file.relative_to(vault_dir)
            print(f"[{i+1}/{len(md_files)}] {rel}")

            try:
                enrich_file(md_file, tmp_dir, stats)
            except Exception as e:
                print(f"    ERROR: {e}")
                stats["errors"] += 1

    print(f"\n{'='*50}")
    print(f"Enrichment complete!")
    print(f"  Files enriched:     {stats['enriched']}")
    print(f"  Articles fetched:   {stats['articles']}")
    print(f"  Videos transcribed: {stats['transcripts']}")
    print(f"  Already processed:  {stats['skipped']}")
    print(f"  No URLs found:      {stats['no_urls']}")
    print(f"  No content fetched: {stats['no_content']}")
    print(f"  Errors:             {stats['errors']}")


if __name__ == "__main__":
    main()

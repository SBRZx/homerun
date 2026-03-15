#!/usr/bin/env python3
"""
Dewey JSON → Obsidian Markdown Converter

Usage:
    python to-obsidian.py <dewey-bookmarks.json> [output-dir]

Reads the JSON exported by dewey-extract.js and produces categorized
markdown files with YAML frontmatter for an Obsidian vault.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "AI-ML": [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "neural net", "gpt", "llm", "openai", "anthropic", "chatgpt",
        "transformer", "diffusion", "stable diffusion", "midjourney",
        "generative", "prompt engineer", "langchain", "rag",
    ],
    "Tech": [
        "programming", "developer", "software", "startup", "saas", "api",
        "javascript", "python", "react", "typescript", "github", "docker",
        "kubernetes", "devops", "web dev", "frontend", "backend", "database",
        "crypto", "blockchain", "web3", "nft",
    ],
    "Health-Fitness": [
        "health", "fitness", "workout", "exercise", "nutrition", "diet",
        "supplement", "protein", "muscle", "cardio", "yoga", "meditation",
        "sleep", "fasting", "biohack", "longevity", "testosterone",
        "gym", "bodyweight", "running",
    ],
    "Psychology-Mindset": [
        "psychology", "mindset", "mental health", "therapy", "cognitive",
        "habit", "motivation", "discipline", "stoic", "philosophy",
        "consciousness", "neuroscience", "dopamine", "anxiety",
        "depression", "mindful", "self-help", "personal development",
    ],
    "Finance-Business": [
        "finance", "investing", "stock", "trading", "money", "wealth",
        "business", "entrepreneur", "revenue", "profit", "market",
        "economy", "real estate", "passive income", "side hustle",
        "freelance", "consulting",
    ],
    "Science": [
        "science", "physics", "biology", "chemistry", "research",
        "study", "experiment", "data", "statistics", "space",
        "astronomy", "climate", "evolution", "genetics", "quantum",
    ],
    "Creative": [
        "design", "art", "photography", "video", "film", "music",
        "writing", "creative", "illustration", "animation", "ui",
        "ux", "branding", "aesthetic",
    ],
    "Productivity": [
        "productivity", "notion", "obsidian", "pkm", "second brain",
        "note-taking", "organization", "workflow", "automation",
        "time management", "todo", "gtd",
    ],
    "Career": [
        "career", "resume", "interview", "hiring", "salary",
        "remote work", "leadership", "management", "networking",
        "linkedin", "job",
    ],
    "Relationships": [
        "relationship", "dating", "marriage", "love", "social",
        "communication", "family", "parenting",
    ],
}


def detect_categories(text: str, labels: list[str]) -> list[str]:
    """Return matching category names based on content + labels."""
    blob = (text + " " + " ".join(labels)).lower()
    hits: list[str] = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in blob:
                hits.append(cat)
                break
    return hits if hits else ["Uncategorized"]


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

SOCIAL_NETWORK_MAP = {
    1: "twitter",
    7: "instagram",
}


def platform_name(social_network_id) -> str:
    try:
        return SOCIAL_NETWORK_MAP.get(int(social_network_id), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def platform_folder(social_network_id) -> str:
    name = platform_name(social_network_id)
    return {"twitter": "Twitter", "instagram": "Instagram"}.get(name, "Other")


# ---------------------------------------------------------------------------
# Sanitise for filenames
# ---------------------------------------------------------------------------

def safe_filename(text: str, max_len: int = 80) -> str:
    """Create a filesystem-safe filename from arbitrary text."""
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]
    return text or "untitled"


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def yaml_escape(value: str) -> str:
    """Escape a string for YAML scalar value."""
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def bookmark_to_md(bm: dict) -> str:
    """Convert a single bookmark dict to an Obsidian markdown string."""

    # --- Extract fields ---
    posted_by = str(bm.get("posted_by") or bm.get("posted_by_nickname") or "unknown")
    nickname = str(bm.get("posted_by_nickname") or posted_by)
    tweet_url = str(bm.get("tweet_url") or "")
    tweet_date = str(bm.get("tweet_date") or "")
    social_network = bm.get("social_network")
    labels = bm.get("labels") or []
    if isinstance(labels, str):
        labels = [l.strip() for l in labels.split(",") if l.strip()]
    folder_id = bm.get("folder_id") or ""
    notes = str(bm.get("notes") or "")
    profile_url = str(bm.get("posted_by_profile_url") or "")

    # Content text
    tweet_content = bm.get("tweet_content")
    if isinstance(tweet_content, dict):
        content_text = str(tweet_content.get("text") or tweet_content.get("full_text") or "")
    elif isinstance(tweet_content, str):
        content_text = tweet_content
    else:
        content_text = ""

    # Media
    tweet_media = bm.get("tweet_media") or []
    if isinstance(tweet_media, dict):
        tweet_media = [tweet_media]

    # Account info
    account = bm.get("account") or {}
    display_name = str(account.get("display_name") or posted_by)

    # Categories
    categories = detect_categories(content_text, labels)

    # --- Build frontmatter ---
    date_str = ""
    if tweet_date:
        try:
            dt = datetime.fromisoformat(tweet_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_str = tweet_date[:10] if len(tweet_date) >= 10 else tweet_date

    tag_list = list(set(labels + categories))
    tags_yaml = ", ".join(yaml_escape(t) for t in tag_list)

    lines = [
        "---",
        f"title: {yaml_escape(posted_by + ' - ' + (date_str or 'undated'))}",
        f"source: {yaml_escape(tweet_url)}",
        f"author: {yaml_escape(nickname)}",
        f"author_display: {yaml_escape(display_name)}",
        f"platform: {yaml_escape(platform_name(social_network))}",
        f"date: {yaml_escape(date_str)}",
        f"tags: [{tags_yaml}]",
    ]
    if folder_id:
        lines.append(f"folder_id: {folder_id}")
    if bm.get("is_archived"):
        lines.append("archived: true")
    lines.append("---")
    lines.append("")

    # --- Content ---
    lines.append("## Content")
    lines.append("")
    if content_text:
        lines.append(content_text.strip())
    else:
        lines.append("*(no text content)*")
    lines.append("")

    # --- Media ---
    if tweet_media:
        lines.append("## Media")
        lines.append("")
        for m in tweet_media:
            if isinstance(m, dict):
                media_url = m.get("media_url") or m.get("link") or ""
                media_type = m.get("type") or "unknown"
                video_src = m.get("video_src") or []
                video_url = m.get("video_url") or ""

                if media_url:
                    if media_type == "video" or video_url or video_src:
                        lines.append(f"- Video: [{media_url}]({media_url})")
                        if video_url:
                            lines.append(f"  - Direct: [{video_url}]({video_url})")
                        for vs in (video_src if isinstance(video_src, list) else []):
                            if vs:
                                lines.append(f"  - Source: [{vs}]({vs})")
                    else:
                        lines.append(f"- ![media]({media_url})")
            elif isinstance(m, str) and m:
                lines.append(f"- ![media]({m})")
        lines.append("")

    # --- Quoted tweet ---
    quoted = bm.get("quoted_tweet")
    if quoted and isinstance(quoted, dict):
        q_text = quoted.get("text") or quoted.get("full_text") or ""
        q_author = quoted.get("posted_by") or quoted.get("user") or ""
        q_url = quoted.get("tweet_url") or ""
        if q_text or q_url:
            lines.append("## Quoted Tweet")
            lines.append("")
            if q_author:
                lines.append(f"**@{q_author}**")
            if q_text:
                lines.append(f"> {q_text.strip()}")
            if q_url:
                lines.append(f"- [Original]({q_url})")
            lines.append("")

    # --- Links ---
    lines.append("## Links")
    lines.append("")
    if tweet_url:
        lines.append(f"- [Original Post]({tweet_url})")
    if profile_url:
        lines.append(f"- [Author Profile]({profile_url})")
    lines.append("")

    # --- Notes ---
    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(notes.strip())
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MOC (Map of Content) generation
# ---------------------------------------------------------------------------

def generate_moc(title: str, entries: list[tuple[str, str]]) -> str:
    """Generate a Map of Content markdown file.

    entries: list of (display_name, relative_path) tuples.
    """
    lines = [
        "---",
        f"title: {yaml_escape(title)}",
        "type: moc",
        "---",
        "",
        f"# {title}",
        "",
    ]
    for name, path in sorted(entries, key=lambda e: e[0].lower()):
        lines.append(f"- [[{path}|{name}]]")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def convert(json_path: str, output_dir: str) -> None:
    print(f"Reading {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    if isinstance(bookmarks, dict):
        # Might be keyed by ID
        bookmarks = list(bookmarks.values())

    print(f"Loaded {len(bookmarks)} bookmarks.")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Track files per category for MOC generation
    category_files: dict[str, list[tuple[str, str]]] = {}
    all_files: list[tuple[str, str]] = []

    for i, bm in enumerate(bookmarks):
        # Determine categories
        tweet_content = bm.get("tweet_content")
        if isinstance(tweet_content, dict):
            content_text = str(tweet_content.get("text") or tweet_content.get("full_text") or "")
        elif isinstance(tweet_content, str):
            content_text = tweet_content
        else:
            content_text = ""

        labels = bm.get("labels") or []
        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",") if l.strip()]

        categories = detect_categories(content_text, labels)
        primary_cat = categories[0]

        # Platform subfolder
        plat_folder = platform_folder(bm.get("social_network"))

        # Build filename
        posted_by = str(bm.get("posted_by") or bm.get("posted_by_nickname") or "unknown")
        tweet_date = str(bm.get("tweet_date") or "")
        date_prefix = ""
        if tweet_date:
            try:
                dt = datetime.fromisoformat(tweet_date.replace("Z", "+00:00"))
                date_prefix = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_prefix = tweet_date[:10] if len(tweet_date) >= 10 else ""

        snippet = safe_filename(content_text[:60]) if content_text else "bookmark"
        fname = safe_filename(f"{date_prefix} {posted_by} - {snippet}") + ".md"

        # Path: output_dir / Platform / Category / file.md
        file_dir = out / plat_folder / primary_cat
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path = file_dir / fname

        # Handle duplicates
        if file_path.exists():
            bm_id = bm.get("id") or i
            file_path = file_dir / f"{file_path.stem}_{bm_id}.md"

        # Write markdown
        md = bookmark_to_md(bm)
        file_path.write_text(md, encoding="utf-8")

        # Track for MOC
        rel = file_path.relative_to(out)
        display = f"{posted_by} ({date_prefix})" if date_prefix else posted_by
        all_files.append((display, str(rel)))
        for cat in categories:
            category_files.setdefault(cat, []).append((display, str(rel)))

        if (i + 1) % 500 == 0:
            print(f"  Processed {i + 1}/{len(bookmarks)}...")

    # --- Generate MOC files ---

    # Root MOC
    root_moc_entries = [(cat, f"_MOC-{cat}.md") for cat in sorted(category_files)]
    root_moc = generate_moc("Bookmarks - Map of Content", root_moc_entries)
    (out / "_MOC.md").write_text(root_moc, encoding="utf-8")

    # Per-category MOC
    for cat, entries in category_files.items():
        cat_moc = generate_moc(f"{cat} Bookmarks", entries)
        (out / f"_MOC-{cat}.md").write_text(cat_moc, encoding="utf-8")

    # Per-platform MOC
    for plat in ["Twitter", "Instagram", "Other"]:
        plat_dir = out / plat
        if plat_dir.exists():
            plat_entries = [(d, p) for d, p in all_files if p.startswith(f"{plat}/")]
            if plat_entries:
                plat_moc = generate_moc(f"{plat} Bookmarks", plat_entries)
                (plat_dir / "_MOC.md").write_text(plat_moc, encoding="utf-8")

    print(f"\nDone! {len(bookmarks)} bookmarks → {output_dir}/")
    print(f"  Categories: {', '.join(sorted(category_files))}")
    print(f"  MOC files: _MOC.md + {len(category_files)} category MOCs")
    print(f"\nOpen {output_dir} as an Obsidian vault to browse.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python to-obsidian.py <dewey-bookmarks.json> [output-dir]")
        print("\n  output-dir defaults to ./obsidian-bookmarks/")
        sys.exit(1)

    json_file = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "./obsidian-bookmarks"
    convert(json_file, output)

# Bookmark Archive & Social Media Memory System — Status & Plan

## Where We Are Now

### What's Been Built (8 scripts)

**Scrapers (JS, paste into browser console):**
1. `x-bookmarks-scrape.js` — X/Twitter bookmarks via GraphQL API interception + DOM fallback
2. `dewey-dom-scrape.js` — Dewey bookmarks via DOM parsing
3. `dewey-api-scrape.js` — Dewey bookmarks via API interception
4. `dewey-extract.js` — Dewey comprehensive (XHR + Angular scope + DOM)
5. `dewey-recon.js` — Diagnostic/reconnaissance for Dewey

**Processors (Python):**
6. `to-obsidian.py` — JSON → Obsidian vault with auto-categorization (11 categories), YAML frontmatter, MOC files
7. `enrich-vault.py` — Fetches article text (trafilatura), linked tweet content (oEmbed), video transcripts (yt-dlp + Whisper)
8. `extract-transcripts.py` — Dedicated video transcript extraction

### Data Captured So Far
- **X/Twitter**: 3,155 bookmarks scraped successfully (x-bookmarks-2026-03-15.json)
- **Dewey**: ~740 bookmarks scraped (dewey-bookmarks-2026-03-15.json, mix of X + Instagram)
- **Total**: ~3,900 bookmarks across both exports

---

## Three Use Cases & Their Status

### 1. Instagram → Substack Research Archive
**Goal**: Archive all saved Instagram posts (especially video/reel content) with full transcripts for Substack writing reference.

**Current status**: PARTIALLY SUPPORTED
- Dewey exports include Instagram bookmarks (social_network=7)
- `to-obsidian.py` maps Instagram to its own folder in the vault
- Video transcription pipeline exists (yt-dlp + Whisper)

**Outstanding issues:**
- [ ] **No native Instagram scraper** — We rely on Dewey for Instagram data, which may not capture all saved posts
- [ ] **Instagram video download is fragile** — yt-dlp can download public Instagram reels but auth-gated content fails silently
- [ ] **No carousel/multi-image support** — Instagram carousels (multiple slides) aren't handled; only first image captured
- [ ] **Instagram captions not reliably extracted** — Dewey may truncate long captions
- [ ] **No Instagram Stories archive** — Stories disappear after 24h and aren't in bookmarks
- [ ] **Substack integration doesn't exist yet** — No way to search/query the archive for writing; it's just Obsidian files

### 2. Instagram → Recipe Extraction
**Goal**: Extract recipe details from saved Instagram posts (usually in the description/caption).

**Current status**: MINIMALLY SUPPORTED
- Instagram posts flow through the same pipeline as everything else
- Caption text is preserved if Dewey captured it

**Outstanding issues:**
- [ ] **No recipe-specific parsing** — Captions contain recipes mixed with hashtags, shoutouts, etc. Need structured extraction (ingredients, steps, servings)
- [ ] **No recipe category** — The 11 auto-categories don't include "Recipes/Food" — recipe posts land in "Uncategorized"
- [ ] **Image-only recipes not handled** — Many recipe posts have ingredients IN the image, not the caption. We decided to skip image AI for now
- [ ] **No recipe template** — Obsidian output is generic tweet format; recipes need a different template (ingredients list, cook time, etc.)

### 3. X/Twitter Bookmark Archive
**Goal**: Full archive of all X bookmarks with enriched content (linked articles, linked tweets, video transcripts).

**Current status**: MOSTLY WORKING
- 3,155 bookmarks captured via API interception + DOM scraping
- Obsidian conversion working with categories, frontmatter, MOC navigation
- Enrichment pipeline handles articles, linked tweets, and video transcription

**Outstanding issues discussed:**
- [x] **First-page bookmarks were missed** — Fixed (commit 820dbe9): now captures DOM before scrolling starts
- [x] **Labels were breaking** — Fixed (commit 531467e): Dewey format sends labels as dicts, not strings
- [x] **Nested f-string syntax error** — Fixed (commit 468f1fb): Python < 3.12 compatibility
- [x] **Linked tweets not fetched** — Fixed (commit 620d1ce): oEmbed API fetches linked tweet content
- [ ] **Images have no descriptions** — Only alt text preserved; most tweets lack alt text. Decided to skip image AI for now
- [ ] **Links to other posts** — Partially fixed via oEmbed. But if an author just pastes a tweet URL (no quote tweet), we only get text via oEmbed which may be incomplete
- [ ] **Thread aggregation missing** — `is_thread` flag is set but individual thread tweets aren't stitched together into one document
- [ ] **No deduplication** — Running the scraper twice creates duplicate bookmarks in JSON; no merge logic
- [ ] **No incremental updates** — Must re-scrape everything each time; no delta detection
- [ ] **Quote tweet content sometimes incomplete** — X's GraphQL sometimes returns truncated quoted tweet text
- [ ] **Engagement stats stale** — Stats are point-in-time from scrape; no refresh mechanism (probably fine)

---

## Remaining Work — Prioritized

### Phase 1: Get the current pipeline fully working end-to-end
1. **Run the Obsidian conversion** on both JSON exports (X + Dewey)
2. **Run enrichment** to fetch articles and linked tweets
3. **Test video transcription** on a few bookmarks to verify yt-dlp + Whisper works
4. **Add "Recipes-Food" category** to `to-obsidian.py` keyword detection
5. **Add deduplication** to `to-obsidian.py` (skip if tweet_id already exists in vault)

### Phase 2: Instagram improvements
6. **Build native Instagram saved-posts scraper** (browser console script for instagram.com/saved/)
   - Instagram's saved posts page loads via GraphQL similar to X
   - Intercept API responses to capture full caption text, media URLs, author info
   - Export same JSON format as X scraper for pipeline compatibility
7. **Instagram caption cleaning** — Strip hashtag blocks, @ mentions, "link in bio" boilerplate from captions
8. **Recipe extraction** — Parse recipe-structured captions into ingredients + steps (regex-based, no AI needed for most)
9. **Recipe Obsidian template** — Custom markdown template for recipe bookmarks with structured sections

### Phase 3: Substack workflow integration
10. **Full-text search index** — Build a simple search script that searches across all vault markdown files (grep-based or sqlite FTS)
11. **Tag-based retrieval** — Ensure tags in frontmatter are searchable for Substack research
12. **Export to Substack draft** — Optional: script to assemble selected bookmarks into a Substack draft outline

### Phase 4: Robustness & maintenance
13. **Incremental scraping** — Compare new scrape against existing JSON, only add new bookmarks
14. **Thread stitching** — Aggregate thread tweets into single documents
15. **Merge script** — Combine multiple JSON exports (different dates, different platforms) into one deduplicated file

---

## Pipeline Commands (current state)

```bash
# Step 1: Scrape (in browser console)
# X: paste x-bookmarks-scrape.js into x.com/i/bookmarks console
# Dewey: paste dewey-dom-scrape.js into getdewey.co console

# Step 2: Convert to Obsidian
cd ~/Documents/obsd
python3 to-obsidian.py x-bookmarks-2026-03-15.json ./obsidian-vault/
python3 to-obsidian.py dewey-bookmarks-2026-03-15.json ./obsidian-vault/

# Step 3: Enrich
pip3 install trafilatura
python3 enrich-vault.py ./obsidian-vault/

# Optional: Video transcripts (requires yt-dlp + whisper)
pip3 install yt-dlp openai-whisper
python3 enrich-vault.py ./obsidian-vault/ --videos-only
```

---

## Architecture Diagram

```
Browser Console Scripts          Python Pipeline              Output
========================    =======================    ================

x.com/i/bookmarks               to-obsidian.py          Obsidian Vault
  └─ x-bookmarks-scrape.js ──→ ┌──────────────┐     ┌─────────────────┐
     (GraphQL + DOM)            │ JSON → .md   │     │ Twitter/         │
                                │ Auto-category│     │   AI-ML/         │
getdewey.co                     │ Frontmatter  │ ──→ │   Tech/          │
  └─ dewey-dom-scrape.js ────→ │ MOC files    │     │ Instagram/       │
     (DOM parsing)              └──────────────┘     │   Recipes-Food/  │
                                                     │ _MOC.md          │
instagram.com/saved/ (TODO)          │               └─────────────────┘
  └─ insta-saved-scrape.js ───→     │                       │
     (GraphQL intercept)            ▼                       ▼
                              enrich-vault.py         Enriched Vault
                              ┌──────────────┐     ┌─────────────────┐
                              │ Article fetch│     │ + Article text   │
                              │ Tweet oEmbed │ ──→ │ + Linked tweets  │
                              │ Video → text │     │ + Transcripts    │
                              └──────────────┘     └─────────────────┘
```

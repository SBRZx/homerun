// =============================================================
// DEWEY DOM SCRAPER — Option B (Guaranteed to work)
// =============================================================
// 1. Go to https://getdewey.co and log in
// 2. Navigate to your bookmarks view (show ALL bookmarks)
// 3. Open DevTools (F12) → Console tab
// 4. Paste this entire script and press Enter
// 5. It will auto-scroll and capture everything visible
// =============================================================

(async function scrapeDeweyDOM() {
  console.log("🔍 DEWEY DOM SCRAPER — Starting...");
  console.log("Phase 1: Auto-scrolling to load all bookmarks...\n");

  // --- Phase 1: Scroll to bottom to load everything ---
  async function scrollToBottom() {
    const scrollable =
      document.querySelector('[class*="scroll"]') ||
      document.querySelector("main") ||
      document.querySelector('[role="main"]') ||
      document.documentElement;

    let lastHeight = 0;
    let sameCount = 0;
    let scrollCount = 0;

    while (sameCount < 5) {
      // stop after 5 consecutive no-change scrolls
      scrollable.scrollTop = scrollable.scrollHeight;
      window.scrollTo(0, document.body.scrollHeight);
      await new Promise((r) => setTimeout(r, 1500));

      const newHeight = Math.max(
        scrollable.scrollHeight,
        document.body.scrollHeight
      );
      scrollCount++;

      if (newHeight === lastHeight) {
        sameCount++;
        console.log(
          `  Scroll ${scrollCount}: no new content (${sameCount}/5 to finish)`
        );
      } else {
        sameCount = 0;
        console.log(
          `  Scroll ${scrollCount}: loaded more content (height: ${lastHeight} → ${newHeight})`
        );
      }
      lastHeight = newHeight;
    }
    console.log(`\n✅ Finished scrolling after ${scrollCount} scrolls.\n`);
  }

  await scrollToBottom();

  // --- Phase 2: Extract bookmark data from DOM ---
  console.log("Phase 2: Extracting bookmark data from DOM...\n");

  const bookmarks = [];

  // Strategy: Try multiple selectors to find bookmark cards/items
  // Dewey likely uses cards or list items for each bookmark
  const selectors = [
    // Common patterns for bookmark/card components
    '[class*="bookmark"]',
    '[class*="tweet"]',
    '[class*="card"]',
    '[class*="post"]',
    '[class*="item"]',
    '[data-testid*="bookmark"]',
    '[data-testid*="tweet"]',
    "article",
    '[role="article"]',
    // Grid/list items
    '[class*="grid"] > div',
    '[class*="list"] > div',
    // Fallback: any link-heavy container
    'li[class]',
  ];

  let items = [];
  for (const selector of selectors) {
    const found = document.querySelectorAll(selector);
    if (found.length > 10) {
      // likely the right selector
      items = found;
      console.log(
        `  Found ${found.length} elements with selector: "${selector}"`
      );
      break;
    }
  }

  if (items.length === 0) {
    // Fallback: grab everything that looks like a content block
    console.log(
      "  No obvious selector found. Using heuristic extraction...\n"
    );
    items = document.querySelectorAll("div[class]");
    // Filter to elements that contain links and text
    items = Array.from(items).filter((el) => {
      const links = el.querySelectorAll("a");
      const text = el.textContent?.trim() || "";
      return (
        links.length >= 1 &&
        text.length > 50 &&
        text.length < 5000 &&
        el.children.length >= 2
      );
    });
    console.log(`  Heuristic found ${items.length} potential bookmark blocks`);
  }

  // Extract data from each item
  items.forEach((item, index) => {
    try {
      // Get all text content
      const text = item.textContent?.trim() || "";

      // Get all links
      const links = Array.from(item.querySelectorAll("a")).map((a) => ({
        text: a.textContent?.trim() || "",
        href: a.href || "",
      }));

      // Get images
      const images = Array.from(item.querySelectorAll("img")).map(
        (img) => img.src || img.dataset?.src || ""
      ).filter(Boolean);

      // Try to find author/username
      const authorEl =
        item.querySelector('[class*="author"]') ||
        item.querySelector('[class*="user"]') ||
        item.querySelector('[class*="name"]') ||
        item.querySelector('[class*="handle"]');
      const author = authorEl?.textContent?.trim() || "";

      // Try to find date
      const dateEl =
        item.querySelector("time") ||
        item.querySelector('[class*="date"]') ||
        item.querySelector('[class*="time"]') ||
        item.querySelector('[datetime]');
      const date =
        dateEl?.getAttribute("datetime") || dateEl?.textContent?.trim() || "";

      // Try to find tags/labels
      const tagEls =
        item.querySelectorAll('[class*="tag"]') ||
        item.querySelectorAll('[class*="label"]') ||
        item.querySelectorAll('[class*="badge"]');
      const tags = Array.from(tagEls)
        .map((t) => t.textContent?.trim())
        .filter(Boolean);

      // Try to find folder
      const folderEl =
        item.querySelector('[class*="folder"]') ||
        item.querySelector('[class*="collection"]') ||
        item.querySelector('[class*="category"]');
      const folder = folderEl?.textContent?.trim() || "";

      // Source link (the original tweet/post URL)
      const sourceLink = links.find(
        (l) =>
          l.href.includes("twitter.com") ||
          l.href.includes("x.com") ||
          l.href.includes("instagram.com") ||
          l.href.includes("bsky.app")
      );

      // External links within the post
      const externalLinks = links.filter(
        (l) =>
          l.href &&
          !l.href.includes("getdewey") &&
          !l.href.includes("javascript:") &&
          !l.href.startsWith("#")
      );

      if (text.length > 10) {
        bookmarks.push({
          index,
          text: text.substring(0, 2000), // cap text length
          author,
          date,
          tags,
          folder,
          sourceUrl: sourceLink?.href || "",
          externalLinks,
          images,
          rawLinks: links,
        });
      }
    } catch (e) {
      console.log(`  Error on item ${index}: ${e.message}`);
    }
  });

  console.log(`\n📊 Extracted ${bookmarks.length} bookmarks\n`);

  if (bookmarks.length === 0) {
    console.log("❌ No bookmarks extracted. Let's debug:");
    console.log("   1. Are your bookmarks visible on the page?");
    console.log("   2. Open Elements tab and inspect a single bookmark card");
    console.log(
      "   3. Tell me the tag name and class of the card container"
    );
    console.log(
      '   4. Run: document.querySelectorAll("YOUR_SELECTOR").length'
    );
    return;
  }

  // --- Phase 3: Download ---
  const blob = new Blob([JSON.stringify(bookmarks, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `dewey-bookmarks-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  console.log(
    `✅ Downloaded ${bookmarks.length} bookmarks to dewey-bookmarks-${new Date().toISOString().slice(0, 10)}.json`
  );
  console.log("\nSample bookmark:");
  console.log(JSON.stringify(bookmarks[0], null, 2));

  // Also store in window for further processing
  window.__deweyBookmarks = bookmarks;
  console.log(
    "\n💡 Bookmarks also stored in window.__deweyBookmarks for further access"
  );
})();

// =============================================================
// DEWEY API SCRAPER — Option A (Recommended)
// =============================================================
// 1. Go to https://getdewey.co and log in
// 2. Open DevTools (F12) → Network tab
// 3. Scroll/browse your bookmarks to trigger API calls
// 4. Look for XHR/Fetch requests — note the domain & auth pattern
// 5. Then come back here and paste this into the Console tab
//
// This script intercepts API calls to find the right endpoints,
// then paginates through all your bookmarks automatically.
// =============================================================

(async function scrapeDeweyAPI() {
  console.log("🔍 DEWEY API SCRAPER — Starting...");
  console.log("Step 1: Intercepting fetch/XHR to discover API patterns...\n");

  // --- Phase 1: Discover API endpoints by monitoring network calls ---
  const discoveredEndpoints = [];
  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    if (
      url.includes("bookmark") ||
      url.includes("tweet") ||
      url.includes("post") ||
      url.includes("save") ||
      url.includes("collection") ||
      url.includes("folder") ||
      url.includes("tag") ||
      url.includes("api")
    ) {
      discoveredEndpoints.push({
        url,
        method: args[1]?.method || "GET",
        headers: args[1]?.headers || {},
      });
      console.log(`📡 Intercepted: ${url}`);
    }
    return originalFetch.apply(this, args);
  };

  // Also intercept XMLHttpRequest
  const originalXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    if (typeof url === "string") {
      discoveredEndpoints.push({ url, method, headers: {} });
      console.log(`📡 XHR Intercepted: ${url}`);
    }
    return originalXHROpen.call(this, method, url, ...rest);
  };

  console.log(
    "✅ Interceptors active. Now scroll through your Dewey bookmarks."
  );
  console.log(
    "   After scrolling a bit, run: window.__deweyCollectResults()\n"
  );

  // --- Phase 2: Once user has scrolled, attempt to paginate the API ---
  window.__deweyCollectResults = async function () {
    console.log("\n📊 Discovered endpoints:");
    discoveredEndpoints.forEach((ep) =>
      console.log(`  ${ep.method} ${ep.url}`)
    );

    // Try to find a bookmark-list endpoint
    const bookmarkEndpoint = discoveredEndpoints.find(
      (ep) =>
        ep.method === "GET" &&
        (ep.url.includes("bookmark") ||
          ep.url.includes("tweet") ||
          ep.url.includes("post") ||
          ep.url.includes("save"))
    );

    if (bookmarkEndpoint) {
      console.log(`\n🎯 Found bookmark endpoint: ${bookmarkEndpoint.url}`);
      console.log(
        "   Attempting to paginate... (this may need manual adjustment)\n"
      );

      // Try fetching with pagination
      const allBookmarks = [];
      let page = 0;
      let hasMore = true;
      const baseUrl = bookmarkEndpoint.url.split("?")[0];

      while (hasMore && page < 200) {
        // safety limit: 200 pages
        try {
          const url = `${baseUrl}?page=${page}&limit=50`;
          const resp = await originalFetch(url, {
            credentials: "include",
          });
          const data = await resp.json();

          const items = Array.isArray(data)
            ? data
            : data.bookmarks ||
              data.tweets ||
              data.posts ||
              data.items ||
              data.data ||
              data.results ||
              [];

          if (items.length === 0) {
            hasMore = false;
          } else {
            allBookmarks.push(...items);
            console.log(
              `  Page ${page}: got ${items.length} items (total: ${allBookmarks.length})`
            );
            page++;
            await new Promise((r) => setTimeout(r, 500)); // rate limit
          }
        } catch (e) {
          console.log(`  Page ${page} failed: ${e.message}`);
          hasMore = false;
        }
      }

      if (allBookmarks.length > 0) {
        downloadJSON(allBookmarks, "dewey-bookmarks-api.json");
        return;
      }
    }

    console.log(
      "\n⚠️  Could not auto-paginate. Falling back to DOM scraper..."
    );
    console.log(
      '   Run the DOM scraper script instead (dewey-dom-scrape.js), or paste the discovered URLs above and we\'ll adjust.\n'
    );
  };

  function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log(
      `\n✅ Downloaded ${data.length} bookmarks to ${filename}`
    );
  }
})();

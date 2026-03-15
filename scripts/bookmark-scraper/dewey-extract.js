// =============================================================
// DEWEY FULL EXTRACTION — Paste into Console on getdewey.co
// =============================================================
// 1. Go to https://getdewey.co/account/#/bookmarks
// 2. Log in and make sure you see some bookmarks
// 3. Open DevTools (F12) → Console
// 4. Type "allow pasting" and press Enter
// 5. Paste this entire script and press Enter
// 6. Wait for it to finish — it will auto-download a JSON file
// =============================================================

(async function extractDewey() {
  console.log("=== DEWEY FULL EXTRACTION ===");
  console.log("Starting...\n");

  var allBookmarks = {};
  var totalFound = 0;

  // --- Method 1: Intercept XHR to discover API endpoint ---
  console.log("[1/3] Setting up XHR interceptor...");

  var apiEndpoint = null;
  var apiHeaders = {};
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

  XMLHttpRequest.prototype.open = function (method, url) {
    this._url = url;
    this._method = method;
    this._headers = {};
    return origOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    this._headers[name] = value;
    return origSetHeader.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function () {
    var self = this;
    var url = this._url || "";
    if (
      url.includes("tweet") ||
      url.includes("bookmark") ||
      url.includes("api")
    ) {
      this.addEventListener("load", function () {
        try {
          var data = JSON.parse(self.responseText);
          var items = Array.isArray(data) ? data : data.bookmarks || data.tweets || data.data || data.results || [];
          if (items.length > 0 && items[0] && items[0].tweet_url) {
            apiEndpoint = url;
            apiHeaders = self._headers || {};
            console.log("API endpoint found:", url);
            console.log("Items in response:", items.length);
            items.forEach(function (item) {
              if (item.id && !allBookmarks[item.id]) {
                allBookmarks[item.id] = cleanBookmark(item);
                totalFound++;
              }
            });
            console.log("Total unique bookmarks so far:", totalFound);
          }
        } catch (e) {}
      });
    }
    return origSend.apply(this, arguments);
  };

  // --- Method 2: Access Angular scope directly ---
  console.log("[2/3] Accessing Angular scope...\n");

  function findBookmarksInScope() {
    var scopes = document.querySelectorAll(".ng-scope");
    for (var i = 0; i < scopes.length; i++) {
      try {
        var scope = angular.element(scopes[i]).scope();
        if (scope && scope.bookmarks && Array.isArray(scope.bookmarks) && scope.bookmarks.length > 0) {
          return { scope: scope, bookmarks: scope.bookmarks };
        }
      } catch (e) {}
    }
    return null;
  }

  var result = findBookmarksInScope();
  if (result) {
    console.log("Found bookmarks in Angular scope:", result.bookmarks.length);
    result.bookmarks.forEach(function (b) {
      if (b.id && !allBookmarks[b.id]) {
        allBookmarks[b.id] = cleanBookmark(b);
        totalFound++;
      }
    });
    console.log("Captured from scope:", totalFound);

    // Try to trigger loading more pages
    console.log("\n[3/3] Auto-scrolling to load all bookmarks...");
    var scope = result.scope;

    // Find the scrollable container
    var scrollEl = document.querySelector(".bookmarks-container") ||
      document.querySelector("[infinite-scroll]") ||
      document.querySelector("main") ||
      document.documentElement;

    var lastCount = 0;
    var stableRounds = 0;
    var scrollRound = 0;
    var maxRounds = 300; // safety limit for ~6000 bookmarks at ~20 per page

    while (stableRounds < 8 && scrollRound < maxRounds) {
      // Scroll to bottom
      window.scrollTo(0, document.body.scrollHeight);
      if (scrollEl !== document.documentElement) {
        scrollEl.scrollTop = scrollEl.scrollHeight;
      }

      // Wait for content to load
      await sleep(800);

      // Re-check scope for new bookmarks
      var updated = findBookmarksInScope();
      if (updated && updated.bookmarks) {
        updated.bookmarks.forEach(function (b) {
          if (b.id && !allBookmarks[b.id]) {
            allBookmarks[b.id] = cleanBookmark(b);
            totalFound++;
          }
        });
      }

      scrollRound++;
      if (totalFound === lastCount) {
        stableRounds++;
      } else {
        stableRounds = 0;
        if (scrollRound % 10 === 0) {
          console.log("  Scroll " + scrollRound + ": " + totalFound + " bookmarks captured");
        }
      }
      lastCount = totalFound;
    }

    console.log("\nScrolling complete. Total bookmarks: " + totalFound);
  } else {
    console.log("Could not find bookmarks in scope.");
    console.log("Waiting for XHR interception... scroll through your bookmarks manually.");
    console.log("Then run: window.__deweyDownload()");
  }

  // --- Download function ---
  window.__deweyDownload = function () {
    var bookmarkArray = Object.values(allBookmarks);
    if (bookmarkArray.length === 0) {
      console.log("No bookmarks captured yet. Keep scrolling!");
      return;
    }
    downloadJSON(bookmarkArray);
  };

  // Auto-download if we got bookmarks
  if (totalFound > 0) {
    var bookmarkArray = Object.values(allBookmarks);
    downloadJSON(bookmarkArray);
  }

  // Store for manual access
  window.__deweyBookmarks = allBookmarks;
  window.__deweyCount = totalFound;
  console.log("\nBookmarks stored in window.__deweyBookmarks (" + totalFound + " total)");
  console.log("To re-download: window.__deweyDownload()");

  // --- Helpers ---
  function cleanBookmark(b) {
    var clean = {};
    var skipKeys = ["$$hashKey", "$$watchers", "$$listeners", "$$childHead", "$$childTail", "$$nextSibling", "$$prevSibling"];
    Object.keys(b).forEach(function (key) {
      if (!skipKeys.includes(key) && !key.startsWith("$$")) {
        var val = b[key];
        if (val && typeof val === "object" && !Array.isArray(val)) {
          // Clean nested objects too
          var nested = {};
          Object.keys(val).forEach(function (nk) {
            if (!nk.startsWith("$$")) nested[nk] = val[nk];
          });
          clean[key] = nested;
        } else {
          clean[key] = val;
        }
      }
    });
    return clean;
  }

  function downloadJSON(data) {
    var json = JSON.stringify(data, null, 2);
    var blob = new Blob([json], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "dewey-bookmarks-" + new Date().toISOString().slice(0, 10) + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log("\n>>> Downloaded " + data.length + " bookmarks as " + a.download);
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }
})();

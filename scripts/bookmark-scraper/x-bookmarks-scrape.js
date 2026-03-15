// =============================================================
// X/TWITTER BOOKMARKS SCRAPER — Paste into Console on x.com
// =============================================================
// 1. Go to https://x.com/i/bookmarks
// 2. Log in and make sure you see your bookmarks
// 3. Open DevTools (F12) → Console
// 4. Type "allow pasting" and press Enter
// 5. Paste this entire script and press Enter
// 6. Wait for it to finish — it will auto-download a JSON file
//
// This script auto-scrolls through your bookmarks, capturing
// tweet data from the DOM. Output is compatible with the
// to-obsidian.py converter.
// =============================================================

(async function scrapeXBookmarks() {
  console.log("=== X/TWITTER BOOKMARKS SCRAPER ===");
  console.log("Starting...\n");

  var allBookmarks = {};
  var totalFound = 0;

  // --- Phase 1: Intercept GraphQL API responses ---
  console.log("[1/2] Setting up API interceptor...");

  var origFetch = window.fetch;
  window.fetch = async function () {
    var resp = await origFetch.apply(this, arguments);
    var url = typeof arguments[0] === "string" ? arguments[0] : (arguments[0] && arguments[0].url) || "";

    if (url.includes("Bookmarks") || url.includes("bookmarks")) {
      try {
        var clone = resp.clone();
        var data = await clone.json();

        // X/Twitter GraphQL response structure
        var instructions = [];
        if (data.data && data.data.bookmark_timeline_v2) {
          instructions = data.data.bookmark_timeline_v2.timeline.instructions || [];
        } else if (data.data && data.data.bookmark_timeline) {
          instructions = data.data.bookmark_timeline.timeline.instructions || [];
        }

        for (var i = 0; i < instructions.length; i++) {
          var entries = instructions[i].entries || [];
          for (var j = 0; j < entries.length; j++) {
            var entry = entries[j];
            try {
              var result = entry.content && entry.content.itemContent && entry.content.itemContent.tweet_results && entry.content.itemContent.tweet_results.result;
              if (!result) continue;

              var tweet = extractTweet(result);
              if (tweet && tweet.id && !allBookmarks[tweet.id]) {
                allBookmarks[tweet.id] = tweet;
                totalFound++;
              }
            } catch (e) {}
          }
        }

        if (totalFound > 0) {
          console.log("API capture: " + totalFound + " bookmarks so far");
        }
      } catch (e) {}
    }
    return resp;
  };

  // --- Phase 2: Capture what's already on screen ---
  console.log("[2/3] Capturing bookmarks already visible on page...");
  await sleep(2000);  // wait for page to fully render
  extractFromDOM();
  console.log("  Captured " + totalFound + " bookmarks from current view");

  // --- Phase 3: Auto-scroll to load all bookmarks ---
  console.log("[3/3] Auto-scrolling to load all bookmarks...\n");

  var lastCount = 0;
  var stableRounds = 0;
  var scrollRound = 0;
  var maxRounds = 500;

  while (stableRounds < 10 && scrollRound < maxRounds) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(1500);

    // Also try to extract from DOM as fallback
    extractFromDOM();

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

  console.log("\nScrolling complete. Scrolling back to top to catch any missed...");
  window.scrollTo(0, 0);
  await sleep(2000);
  extractFromDOM();
  console.log("Final total: " + totalFound + " bookmarks");

  // --- Download ---
  if (totalFound > 0) {
    var bookmarkArray = Object.values(allBookmarks);
    downloadJSON(bookmarkArray);
  } else {
    console.log("No bookmarks captured via API. Trying DOM extraction...");
    extractFromDOM();
    var bookmarkArray = Object.values(allBookmarks);
    if (bookmarkArray.length > 0) {
      downloadJSON(bookmarkArray);
    } else {
      console.log("Could not capture bookmarks. Try scrolling manually, then run: window.__xDownload()");
    }
  }

  // Store for manual access
  window.__xBookmarks = allBookmarks;
  window.__xDownload = function () {
    var arr = Object.values(allBookmarks);
    if (arr.length === 0) {
      console.log("No bookmarks captured yet.");
      return;
    }
    downloadJSON(arr);
  };

  console.log("\nBookmarks stored in window.__xBookmarks (" + totalFound + " total)");
  console.log("To re-download: window.__xDownload()");

  // --- Helpers ---

  function extractTweet(result) {
    // Handle tweet with tombstone
    if (result.__typename === "TweetWithVisibilityResults") {
      result = result.tweet;
    }
    if (!result || !result.legacy) return null;

    var legacy = result.legacy;
    var core = result.core || {};
    var userResult = core.user_results && core.user_results.result;
    var userLegacy = userResult && userResult.legacy || {};

    var mediaItems = [];
    var extMedia = legacy.extended_entities && legacy.extended_entities.media || [];
    for (var m = 0; m < extMedia.length; m++) {
      var media = extMedia[m];
      var videoSrc = [];
      if (media.video_info && media.video_info.variants) {
        for (var v = 0; v < media.video_info.variants.length; v++) {
          var variant = media.video_info.variants[v];
          if (variant.content_type === "video/mp4") {
            videoSrc.push(variant.url);
          }
        }
      }
      mediaItems.push({
        media_url: media.media_url_https || media.media_url || "",
        type: media.type || "photo",
        video_src: videoSrc,
        video_url: videoSrc.length > 0 ? videoSrc[videoSrc.length - 1] : "",
      });
    }

    // Quoted tweet
    var quotedTweet = null;
    if (result.quoted_status_result && result.quoted_status_result.result) {
      var qr = result.quoted_status_result.result;
      if (qr.__typename === "TweetWithVisibilityResults") qr = qr.tweet;
      if (qr && qr.legacy) {
        var qUser = qr.core && qr.core.user_results && qr.core.user_results.result && qr.core.user_results.result.legacy || {};
        quotedTweet = {
          text: qr.legacy.full_text || "",
          posted_by: qUser.screen_name || "",
          tweet_url: "https://x.com/" + (qUser.screen_name || "unknown") + "/status/" + qr.legacy.id_str,
        };
      }
    }

    return {
      id: legacy.id_str || result.rest_id || "",
      tweet_id: legacy.id_str || result.rest_id || "",
      tweet_date: legacy.created_at || "",
      posted_by: userLegacy.screen_name || "",
      posted_by_nickname: userLegacy.name || "",
      posted_by_profile_url: "https://x.com/" + (userLegacy.screen_name || ""),
      tweet_content: {
        text: legacy.full_text || "",
      },
      tweet_url: "https://x.com/" + (userLegacy.screen_name || "unknown") + "/status/" + (legacy.id_str || result.rest_id),
      tweet_media: mediaItems,
      labels: [],
      folder_id: "",
      notes: "",
      social_network: 1,
      is_quoted_tweet: !!quotedTweet,
      quoted_tweet: quotedTweet,
      account: {
        display_name: userLegacy.name || "",
        nick_name: userLegacy.screen_name || "",
        profile_url: "https://x.com/" + (userLegacy.screen_name || ""),
      },
    };
  }

  function extractFromDOM() {
    var articles = document.querySelectorAll("article[data-testid='tweet']");
    for (var i = 0; i < articles.length; i++) {
      try {
        var article = articles[i];

        // Get tweet link to extract ID
        var timeLink = article.querySelector("a[href*='/status/']");
        if (!timeLink) continue;
        var href = timeLink.getAttribute("href");
        var parts = href.split("/status/");
        if (parts.length < 2) continue;
        var tweetId = parts[1].split("/")[0].split("?")[0];
        var username = parts[0].replace("/", "");

        if (allBookmarks[tweetId]) continue;

        // Get text
        var textEl = article.querySelector("[data-testid='tweetText']");
        var text = textEl ? textEl.textContent.trim() : "";

        // Get display name
        var nameEl = article.querySelector("[data-testid='User-Name']");
        var displayName = "";
        if (nameEl) {
          var spans = nameEl.querySelectorAll("span");
          if (spans.length > 0) displayName = spans[0].textContent.trim();
        }

        // Get time
        var timeEl = article.querySelector("time");
        var dateStr = timeEl ? (timeEl.getAttribute("datetime") || timeEl.textContent) : "";

        // Get images
        var imgs = article.querySelectorAll("img[src*='pbs.twimg.com/media']");
        var mediaItems = [];
        for (var m = 0; m < imgs.length; m++) {
          mediaItems.push({
            media_url: imgs[m].src,
            type: "photo",
            video_src: [],
            video_url: "",
          });
        }

        // Check for video
        var videoEl = article.querySelector("video");
        if (videoEl) {
          mediaItems.push({
            media_url: videoEl.poster || "",
            type: "video",
            video_src: [videoEl.src || ""],
            video_url: videoEl.src || "",
          });
        }

        allBookmarks[tweetId] = {
          id: tweetId,
          tweet_id: tweetId,
          tweet_date: dateStr,
          posted_by: username,
          posted_by_nickname: displayName,
          posted_by_profile_url: "https://x.com/" + username,
          tweet_content: { text: text },
          tweet_url: "https://x.com/" + username + "/status/" + tweetId,
          tweet_media: mediaItems,
          labels: [],
          folder_id: "",
          notes: "",
          social_network: 1,
          is_quoted_tweet: false,
          quoted_tweet: null,
          account: {
            display_name: displayName,
            nick_name: username,
            profile_url: "https://x.com/" + username,
          },
        };
        totalFound++;
      } catch (e) {}
    }
  }

  function downloadJSON(data) {
    var json = JSON.stringify(data, null, 2);
    var blob = new Blob([json], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "x-bookmarks-" + new Date().toISOString().slice(0, 10) + ".json";
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

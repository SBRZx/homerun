// =============================================================
// DEWEY RECON — Run this FIRST
// =============================================================
// 1. Go to https://getdewey.co and log in
// 2. Navigate to your bookmarks (make sure some are visible)
// 3. Open DevTools (F12) → Console tab
// 4. Paste this script and press Enter
// 5. Share the output with me so I can tune the scraper
// =============================================================

(function deweyRecon() {
  console.log("🔍 DEWEY RECON — Analyzing page structure...\n");

  // 1. What framework is Dewey using?
  const framework = {
    react: !!document.querySelector("[data-reactroot], [data-react-helmet]") || !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__,
    nextjs: !!document.querySelector("#__next") || !!window.__NEXT_DATA__,
    vue: !!window.__VUE__,
    angular: !!window.ng,
    svelte: !!document.querySelector("[class*='svelte']"),
  };
  console.log("Framework detection:", JSON.stringify(framework));

  // 2. Check for Next.js data (goldmine if present)
  if (window.__NEXT_DATA__) {
    console.log("\n🎯 __NEXT_DATA__ found! Props:");
    console.log(JSON.stringify(Object.keys(window.__NEXT_DATA__), null, 2));
    if (window.__NEXT_DATA__.props?.pageProps) {
      const pp = window.__NEXT_DATA__.props.pageProps;
      console.log("pageProps keys:", Object.keys(pp));
      // Check if bookmarks are pre-rendered
      for (const key of Object.keys(pp)) {
        const val = pp[key];
        if (Array.isArray(val) && val.length > 0) {
          console.log(`  📦 ${key}: Array of ${val.length} items`);
          console.log(`     Sample:`, JSON.stringify(val[0]).substring(0, 300));
        }
      }
    }
  }

  // 3. Check for any global state stores
  const globals = {};
  for (const key of Object.keys(window)) {
    if (
      key.startsWith("__") &&
      !key.startsWith("__zone") &&
      !key.startsWith("__coverage")
    ) {
      globals[key] = typeof window[key];
    }
  }
  console.log("\nInteresting globals:", JSON.stringify(globals, null, 2));

  // 4. Service worker / cache analysis
  if ("caches" in window) {
    caches.keys().then((names) => {
      console.log("\nCache storage:", names);
    });
  }

  // 5. localStorage keys (may contain cached bookmarks)
  const lsKeys = Object.keys(localStorage);
  console.log("\nlocalStorage keys:", lsKeys);
  for (const key of lsKeys) {
    const val = localStorage.getItem(key);
    if (val && val.length > 100) {
      console.log(`  ${key}: ${val.length} chars`);
      // Check if it's JSON with bookmark data
      try {
        const parsed = JSON.parse(val);
        if (Array.isArray(parsed) && parsed.length > 5) {
          console.log(`    🎯 Array of ${parsed.length} items!`);
          console.log(`    Sample:`, JSON.stringify(parsed[0]).substring(0, 200));
        } else if (typeof parsed === "object") {
          console.log(`    Keys:`, Object.keys(parsed).slice(0, 10));
        }
      } catch (e) {}
    }
  }

  // 6. sessionStorage
  const ssKeys = Object.keys(sessionStorage);
  console.log("\nsessionStorage keys:", ssKeys);

  // 7. IndexedDB databases
  if (window.indexedDB?.databases) {
    window.indexedDB.databases().then((dbs) => {
      console.log("\nIndexedDB databases:", dbs.map((d) => d.name));
    });
  }

  // 8. DOM structure analysis
  console.log("\n--- DOM ANALYSIS ---");

  // Find the main content area
  const mainContainers = [
    "main",
    '[role="main"]',
    "#__next > div",
    "#app > div",
    "#root > div",
  ];
  for (const sel of mainContainers) {
    const el = document.querySelector(sel);
    if (el) {
      console.log(
        `\n${sel}: ${el.children.length} children, classes="${el.className}"`
      );
    }
  }

  // Count elements by tag and find likely bookmark containers
  const allDivs = document.querySelectorAll("div[class]");
  const classCounts = {};
  allDivs.forEach((div) => {
    const cls = div.className;
    if (typeof cls === "string" && cls.length > 0 && cls.length < 100) {
      classCounts[cls] = (classCounts[cls] || 0) + 1;
    }
  });

  // Find classes that repeat many times (likely bookmark cards)
  const repeating = Object.entries(classCounts)
    .filter(([, count]) => count >= 5)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20);

  console.log("\nMost repeated div classes (likely bookmark cards):");
  repeating.forEach(([cls, count]) => {
    const sample = document.querySelector(`div.${CSS.escape(cls)}`);
    const textLen = sample?.textContent?.trim().length || 0;
    const linkCount = sample?.querySelectorAll("a").length || 0;
    const imgCount = sample?.querySelectorAll("img").length || 0;
    console.log(
      `  "${cls}" × ${count}  (text: ${textLen} chars, links: ${linkCount}, imgs: ${imgCount})`
    );
  });

  // 9. Check all link patterns
  const allLinks = Array.from(document.querySelectorAll("a[href]"));
  const linkPatterns = {};
  allLinks.forEach((a) => {
    try {
      const host = new URL(a.href).hostname;
      linkPatterns[host] = (linkPatterns[host] || 0) + 1;
    } catch (e) {}
  });
  console.log(
    "\nLink domains on page:",
    JSON.stringify(linkPatterns, null, 2)
  );

  // 10. Network intercept setup for API discovery
  console.log("\n--- SETTING UP API MONITOR ---");
  console.log("Now scroll through your bookmarks. API calls will be logged.\n");

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    const resp = await origFetch.apply(this, args);
    // Clone to inspect without consuming
    const clone = resp.clone();
    try {
      const ct = clone.headers.get("content-type") || "";
      if (ct.includes("json")) {
        const data = await clone.json();
        const size = Array.isArray(data)
          ? data.length
          : typeof data === "object"
            ? Object.keys(data).length
            : 0;
        console.log(`📡 FETCH ${url} → ${size} items/keys`);
        if (Array.isArray(data) && data.length > 0) {
          console.log(`   First item keys: ${Object.keys(data[0])}`);
        } else if (data.data && Array.isArray(data.data)) {
          console.log(
            `   data[] has ${data.data.length} items, keys: ${Object.keys(data.data[0] || {})}`
          );
        }
      }
    } catch (e) {}
    return resp;
  };

  console.log("✅ Recon complete. Now:");
  console.log("   1. Scroll through your bookmarks to trigger API calls");
  console.log("   2. Copy ALL console output and share with me");
  console.log("   3. I'll tune the scraper to Dewey's exact structure");
})();

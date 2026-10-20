/* just-here soft-launch SW: shell cache only */
const CACHE = "just-here-shell-v60";
const SHELL = [
  "/",
  "/static/styles.css?v=20261019-my1",
  "/static/app.js?v=20261019-my1",
  "/static/instagram.js?v=20260926-ig1",
  "/static/badges.js?v=20260930-badges1",
  "/static/instagram-places.json",
  "/static/auth.js?v=20261004-auth1",
  "/static/story.js?v=20260930-receipt2",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k.startsWith("just-here-shell-") && k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Only the public shell and non-HTML static assets are cacheable.
  // MY, admin, merchant, previews, API responses and credentials bypass caches entirely.
  const publicShell = url.pathname === "/" && !url.search;
  const staticAsset = url.pathname.startsWith("/static/") &&
    /\.(css|js|png|jpg|jpeg|webp|svg|ico|woff2?|json)$/.test(url.pathname);
  if ((!publicShell && !staticAsset && url.pathname !== "/manifest.webmanifest") ||
      req.headers.has("X-Guest-Token") || req.headers.has("X-Admin-Token") ||
      req.headers.has("X-Merchant-Key")) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && !res.redirected && !/no-store|private/i.test(res.headers.get("Cache-Control") || "")) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || Response.error()))
  );
});

/* pykofinder service worker
 *
 * Strategy:
 *   - App shell (/f/) and static assets (icons, manifest) → cache-first,
 *     updated in background (stale-while-revalidate).
 *   - Dynamic HTMX partials (/click, /restore, /raw, /vpage, /sse/*)
 *     → network-only; never cached.
 *   - Everything else → network-first with shell fallback.
 */

const CACHE = "pykofinder-v2";

const PRECACHE = [
  "/f/",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon.svg",
];

/* Paths whose responses must never be served from cache. */
const NETWORK_ONLY_PREFIXES = [
  "/f/",
  "/click",
  "/restore",
  "/raw",
  "/vpage",
  "/sse/",
  "/open-link",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  /* Only handle same-origin requests. */
  if (url.origin !== location.origin) return;

  const path = url.pathname;

  /* Dynamic endpoints – always hit the network. */
  if (NETWORK_ONLY_PREFIXES.some((p) => path.startsWith(p))) {
    return; /* browser default: network */
  }

  /* App shell + icons: stale-while-revalidate. */
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request);
      const networkFetch = fetch(event.request)
        .then((response) => {
          if (response.ok) cache.put(event.request, response.clone());
          return response;
        })
        .catch(() => null);

      /* Return cached immediately, refresh in background. */
      return cached || networkFetch || new Response("Offline", { status: 503 });
    }),
  );
});

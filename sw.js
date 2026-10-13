/* SameGame service worker — offline support.
 *
 * Strategy:
 *  - navigation requests (the app shell): network-first, fall back to the cache
 *    when offline; a successful load refreshes the cached copy.
 *  - other same-origin GETs (manifest, icons): cache-first, fill on miss.
 *
 * The browser re-fetches this script on every page load and reinstalls it when
 * its bytes change, so no version bump is needed here — just redeploy.
 */
const CACHE = 'samegame-v1';
const PRECACHE = ['./', 'index.html', 'manifest.webmanifest',
                  'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || !req.url.startsWith(self.location.origin)) return;

  if (req.mode === 'navigate') {
    // Network-first: fresh page when online, cached shell when offline.
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || caches.match('index.html')))
    );
    return;
  }

  // Cache-first for static assets.
  e.respondWith(
    caches.match(req).then((hit) =>
      hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
    )
  );
});

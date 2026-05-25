const CACHE = 'anipulse-v1';
const PRECACHE = [
  '/',
  '/discover/',
  '/static/icons/icon-192.svg',
  '/static/icons/icon-512.svg',
  '/static/css/anipulse.css',
];

const RUNTIME_CACHE = [
  'cdn.jsdelivr.net',
  'fonts.googleapis.com',
  'cdnjs.cloudflare.com',
  'graphql.anilist.co',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => {
      c.addAll(PRECACHE);
      // Skip waiting so new SW activates immediately
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // AniList API: network-only (fresh data)
  if (url.hostname === 'graphql.anilist.co') {
    return;
  }

  // CDN assets: cache-first
  if (RUNTIME_CACHE.some((host) => url.hostname.includes(host))) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        const fetched = fetch(e.request).then((res) => {
          const clone = res.clone();
          if (res.ok) caches.open(CACHE).then((c) => c.put(e.request, clone));
          return res;
        });
        return cached || fetched;
      })
    );
    return;
  }

  // Same-origin: network-first, fallback to cache
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const clone = res.clone();
        if (res.ok && res.type === 'basic') {
          caches.open(CACHE).then((c) => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

const CACHE_NAME = 'anipulse-v1';
const STATIC_ASSETS = [
    '/',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
            .catch(() => { })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    if (e.request.url.startsWith('http') && !e.request.url.includes('127.0.0.1') && !e.request.url.includes('localhost')) {
        e.respondWith(
            caches.match(e.request).then((r) => r || fetch(e.request).then((res) => {
                if (res.status === 200) {
                    const clone = res.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
                }
                return res;
            }).catch(() => caches.match('/')))
        );
        return;
    }
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request).then((r) => r || new Response('Offline — check your connection', { status: 503 })))
    );
});

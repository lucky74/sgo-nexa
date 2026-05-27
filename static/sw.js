const CACHE_NAME = 'sgo-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/script.js',
  '/static/manifest.json',
];

// Install — cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — hapus cache lama
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first, fallback ke cache
self.addEventListener('fetch', event => {
  // Skip non-GET dan API calls
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/') || 
      event.request.url.includes('/webhook') ||
      event.request.url.includes('/submit_order')) return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache response baru untuk static assets
        if (response.ok && event.request.url.includes('/static/')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

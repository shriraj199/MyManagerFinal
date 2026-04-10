const CACHE_NAME = 'themanager-v1';
const urlsToCache = [
  '/',
  '/static/core/pwa/manifest.json',
  '/static/core/pwa/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  // Fix: Do not intercept external CDN requests (Tailwind, Lucide, etc.) to avoid CORS issues
  if (event.request.url.startsWith('http') && !event.request.url.includes(self.location.origin)) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});

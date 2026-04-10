const CACHE_NAME = 'themanager-v1';
const urlsToCache = [
  '/',
  '/login/',
  '/register/',
  '/maintenance/',
  '/static/core/pwa/logo.png',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/lucide@latest'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  // Only handle GET requests for caching
  if (event.request.method !== 'GET') return;

  // Fix: Do not intercept external CDN requests (Tailwind, Lucide, etc.) to avoid CORS issues
  if (event.request.url.startsWith('http') && !event.request.url.includes(self.location.origin)) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});

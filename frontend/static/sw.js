const CACHE = 'physlab-v3';
const STATIC = [
  '/static/logo.svg',
  '/static/manifest.json',
  'https://fonts.googleapis.com/css2?family=Unbounded:wght@700;800;900&family=Sora:wght@400;600;700;800&family=DM+Sans:wght@400;500;600&display=swap',
  'https://unpkg.com/@phosphor-icons/web',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Always network for API, socket, and HTML pages
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/socket.io')) return;
  if (!url.pathname.includes('.') || url.pathname.endsWith('.html')) return;

  // Network-first for CSS and JS so updates reflect on normal reload
  if (url.pathname.endsWith('.css') || url.pathname.endsWith('.js')) {
    e.respondWith(
      fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Cache-first for everything else (fonts, icons, images)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
    })
  );
});

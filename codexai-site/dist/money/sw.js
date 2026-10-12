/* Offline shell for the new money demo at the original URL. Legacy data remains in localStorage. */
const CACHE = 'codexai-money-offline-v4:' + self.registration.scope;
const ASSETS = [
  './', './index.html', '../assets/code-x-ai-logo.png'
].map(path => new URL(path, self.registration.scope).href);
const PROJECT_ROOT = new URL('../', self.registration.scope).href;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith('codexai-money-offline-') && key.endsWith(self.registration.scope) && key !== CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || !request.url.startsWith(PROJECT_ROOT)) return;
  event.respondWith(fetch(request).then(response => {
    if (response.ok) event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, response.clone())));
    return response;
  }).catch(() => caches.match(request, {ignoreSearch: true})));
});

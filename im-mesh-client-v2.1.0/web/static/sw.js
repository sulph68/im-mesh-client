/**
 * Service Worker for Im Mesh Client
 * Provides offline caching of static assets (UI shell).
 * API requests are always network-first (no caching of live mesh data).
 */

const CACHE_NAME = 'im-mesh-v26';
const STATIC_ASSETS = [
    '/',
    '/static/storage.js',
    '/static/js/app_core.js',
    '/static/js/app_connection.js',
    '/static/js/app_data.js',
    '/static/js/app_nodes.js',
    '/static/js/app_ui.js',
    '/static/js/app_sessions.js',
    '/static/js/app_messages.js',
    '/static/js/app_images.js',
    '/static/js/app_init.js',
    '/static/css/base.css',
    '/static/css/layout.css',
    '/static/css/components.css',
    '/static/css/panels.css',
    '/static/css/mobile.css',
    '/static/manifest.json',
    '/static/icon-192.svg',
    '/static/icon-512.svg'
];

// Install: pre-cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: network-first for everything to avoid stale cache issues.
// Falls back to cache only when network is unavailable (offline support).
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Never cache API requests or WebSocket upgrades
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) {
        return;
    }

    // Network-first: always try network, fall back to cache for offline
    event.respondWith(
        fetch(event.request).then((response) => {
            if (response.ok && url.origin === self.location.origin) {
                // Cache the fresh response (strip query string for cache key)
                const cacheKey = new Request(url.origin + url.pathname);
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(cacheKey, responseClone);
                });
            }
            return response;
        }).catch(() => {
            // Network failed - try cache (strip query string for lookup)
            const cacheKey = new Request(url.origin + url.pathname);
            return caches.match(cacheKey);
        })
    );
});

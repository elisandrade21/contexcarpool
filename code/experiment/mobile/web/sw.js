// Minimal service worker so the app can be installed; always fetches from the network (rules and data must stay current).
self.addEventListener("install",e=>self.skipWaiting());
self.addEventListener("activate",e=>self.clients.claim());
self.addEventListener("fetch",e=>{});

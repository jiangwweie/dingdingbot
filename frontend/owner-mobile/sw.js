/* Static shell only: never cache API, cookies, trade intents or market facts. */
const CACHE='brc-owner-mobile-v1';
const ASSETS=['./','./index.html','./styles.css','./app.js','./manifest.webmanifest','./icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('brc-owner-mobile-')&&k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==location.origin||!url.pathname.startsWith('/mobile/')||url.pathname.startsWith('/api/'))return;
 event.respondWith(fetch(event.request).catch(async()=>await caches.match(event.request)||new Response('连接不可用',{status:503,headers:{'Content-Type':'text/plain;charset=utf-8'}})));
});

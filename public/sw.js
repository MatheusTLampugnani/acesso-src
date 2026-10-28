// Service Worker do VisionStock (ALMOX) — suporte offline do PWA.
// Troque a versão quando mudar a estratégia de cache; os arquivos do build já têm hash no nome.
const CACHE_NAME = 'almox-v4';
// Caminho onde o app está publicado ("/" ou um subcaminho como "/visionstock/")
const BASE = new URL(self.registration.scope).pathname;
const INDEX = `${BASE}index.html`;
const SHELL = [BASE, INDEX, `${BASE}manifest.json`, `${BASE}favicon.ico`, `${BASE}pwa-192x192.png`, `${BASE}pwa-512x512.png`];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const guardar = (request, response) => {
  if (response && response.ok && response.type === 'basic') {
    const copia = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, copia));
  }
  return response;
};

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Só GET dos arquivos do próprio app; API do drone, Supabase e o Portal de Acesso (/acesso/, que diz
  // quem está logado) vão direto para a rede — servir esses do cache trocaria o operador com atraso
  if (request.method !== 'GET' || url.origin !== self.location.origin
    || !url.pathname.startsWith(BASE) || url.pathname.startsWith(`${BASE}api/`)) return;

  // Navegação: rede primeiro (pega versão nova), cache como reserva offline
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => guardar(INDEX, res))
        .catch(() => caches.match(INDEX))
    );
    return;
  }

  // Arquivos do build (assets/*.js|css com hash): cache primeiro e guarda na primeira visita,
  // para o app abrir offline mesmo sem ter sido pré-cacheado na instalação
  if (url.pathname.startsWith(`${BASE}assets/`)) {
    event.respondWith(
      caches.match(request).then((cache) => cache || fetch(request).then((res) => guardar(request, res)))
    );
    return;
  }

  // Demais arquivos estáticos: devolve o cache e atualiza em segundo plano
  event.respondWith(
    caches.match(request).then((cache) => {
      const rede = fetch(request).then((res) => guardar(request, res)).catch(() => cache || Response.error());
      return cache || rede;
    })
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

/* Service worker da Sora (PWA): só a notificação do "Precisa de você" (Web Push).
 * Não guarda nada em cache e não intercepta pedidos: o app continua vindo sempre do servidor.
 * A carga vem do backend (app/push.py): { titulo, corpo, url, tag }, sem o conteúdo do pedido. */
self.addEventListener('install', () => { self.skipWaiting(); });
self.addEventListener('activate', evento => { evento.waitUntil(self.clients.claim()); });

self.addEventListener('push', evento => {
  let dados = {};
  try { dados = evento.data ? evento.data.json() : {}; } catch { dados = {}; }
  const titulo = typeof dados.titulo === 'string' ? dados.titulo : 'Sora';
  evento.waitUntil(self.registration.showNotification(titulo, {
    body: typeof dados.corpo === 'string' ? dados.corpo : 'Um bot precisa de você.',
    tag: typeof dados.tag === 'string' ? dados.tag : undefined,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    lang: 'pt-BR',
    data: { url: typeof dados.url === 'string' && dados.url.startsWith('/') ? dados.url : '/' },
  }));
});

self.addEventListener('notificationclick', evento => {
  evento.notification.close();
  const destino = new URL(evento.notification.data && evento.notification.data.url || '/', self.location.origin).href;
  evento.waitUntil((async () => {
    const janelas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const janela of janelas) {
      if (new URL(janela.url).origin === self.location.origin) {
        await janela.focus();
        if ('navigate' in janela) await janela.navigate(destino);
        return;
      }
    }
    await self.clients.openWindow(destino);
  })());
});

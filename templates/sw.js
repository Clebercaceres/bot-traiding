self.addEventListener('push', e => {
  let data = {};
  try { data = JSON.parse(e.data.text()); } catch {}
  e.waitUntil(
    self.registration.showNotification(data.title || 'TradeBot', {
      body: data.body || '',
      icon: '/favicon.ico',
      tag: data.tag || 'tradebot',
      renotify: true,
      requireInteraction: data.tag === 'signal', // señales requieren acción manual
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow('/'));
});

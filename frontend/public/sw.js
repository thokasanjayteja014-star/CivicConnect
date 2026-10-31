/* CivicConnect service worker: shows browser push notifications and opens the linked page on click. */
self.addEventListener("push", (event) => {
  let data = { title: "CivicConnect", body: "You have a new update.", url: "/notifications" };
  try { data = { ...data, ...event.data.json() }; } catch (e) { /* plain text or empty payload */ }
  event.waitUntil(self.registration.showNotification(data.title, { body: data.body, data: { url: data.url }, tag: data.url }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/notifications";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ("focus" in w) { w.navigate(url); return w.focus(); }
      }
      return self.clients.openWindow(url);
    }),
  );
});

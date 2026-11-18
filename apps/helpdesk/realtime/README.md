# realtime

Do not rename this folder. Frappe's realtime server loads `<app>/realtime/handlers.js` by this exact path
(`apps/frappe/realtime/index.js`), so `hd-realtime/` would silently disable the ticket-viewer, typing and ping handlers.

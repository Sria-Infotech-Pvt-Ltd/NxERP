import { io } from "socket.io-client";
import { socketio_port } from "../../../../sites/common_site_config.json";

// extend window object
declare global {
  interface Window {
    site_name: string;
  }
}

export function initSocket() {
  let host = window.location.hostname;
  let siteName = window.site_name || host;
  // A built bundle is served by the web server, which also proxies /socket.io: use the page's own origin, as
  // Frappe's desk client does. Only the Vite dev server needs the separate socketio_port.
  if (!import.meta.env.DEV) {
    return io(`${window.location.origin}/${siteName}`, {
      withCredentials: true,
      reconnectionAttempts: 5,
    });
  }
  let port = window.location.port ? `:${socketio_port}` : "";
  let protocol = port ? "http" : "https";
  let url = `${protocol}://${host}${port}/${siteName}`;

  const socket = io(url, {
    withCredentials: true,
    reconnectionAttempts: 5,
  });

  return socket;
}

export const socket = initSocket();

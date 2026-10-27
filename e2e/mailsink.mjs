// A minimal SMTP capture server for the tests: accepts mail on a local port, keeps it in memory, sends nothing
// anywhere. Enough of RFC 5321 for Frappe's smtplib client (no TLS, no auth).
import net from "node:net";

export function startMailSink(port = 2525) {
	const messages = [];
	const server = net.createServer((socket) => {
		let buffer = "";
		let inData = false;
		let from = "";
		let to = [];
		let data = [];
		const reply = (line) => socket.write(line + "\r\n");
		reply("220 nxerp-e2e-sink ESMTP");
		socket.on("data", (chunk) => {
			buffer += chunk.toString("utf-8");
			let index;
			while ((index = buffer.indexOf("\r\n")) !== -1) {
				const line = buffer.slice(0, index);
				buffer = buffer.slice(index + 2);
				if (inData) {
					if (line === ".") {
						inData = false;
						messages.push({ from, to, raw: data.join("\r\n") });
						data = [];
						reply("250 OK queued");
					} else {
						data.push(line.startsWith("..") ? line.slice(1) : line);
					}
					continue;
				}
				const command = line.toUpperCase();
				if (command.startsWith("EHLO")) {
					socket.write("250-nxerp-e2e-sink\r\n250 8BITMIME\r\n");
				} else if (command.startsWith("HELO")) reply("250 nxerp-e2e-sink");
				else if (command.startsWith("MAIL FROM")) {
					from = line.slice(10).replace(/[<>]/g, "").trim();
					to = [];
					reply("250 OK");
				} else if (command.startsWith("RCPT TO")) {
					to.push(line.slice(8).replace(/[<>]/g, "").trim());
					reply("250 OK");
				} else if (command === "DATA") {
					inData = true;
					reply("354 End data with <CR><LF>.<CR><LF>");
				} else if (command === "RSET") reply("250 OK");
				else if (command === "NOOP") reply("250 OK");
				else if (command === "QUIT") {
					reply("221 Bye");
					socket.end();
				} else reply("502 Command not implemented");
			}
		});
		socket.on("error", () => {});
	});
	return new Promise((resolve) => {
		server.listen(port, "127.0.0.1", () =>
			resolve({
				messages,
				stop: () => new Promise((done) => server.close(() => done())),
				/** The newest message for `recipient`, decoded enough to read links and codes out of it. */
				latestFor(recipient) {
					const found = [...messages].reverse().find((m) => m.to.some((t) => t.toLowerCase() === recipient.toLowerCase()));
					return found ? { ...found, text: decode(found.raw) } : null;
				},
			}),
		);
	});
}

/** Undo quoted-printable / base64 bodies so assertions can read the plain text. */
export function decode(raw) {
	let text = raw;
	text = text.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
	const blocks = [...raw.matchAll(/Content-Transfer-Encoding: base64\r?\n\r?\n([A-Za-z0-9+/=\r\n]+)/gi)];
	for (const block of blocks) text += "\n" + Buffer.from(block[1].replace(/\s+/g, ""), "base64").toString("utf-8");
	return text;
}

// Renders the link-preview image (1200x630) from the real page.
// Usage: node scripts/og_image.mjs [baseUrl] [outFile]   (needs chromium and a running server)
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8000/";
const OUT = process.argv[3] || "src/watt_brief/static/og.png";
const PORT = 9334;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn("chromium", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "wb-og-"))}`,
  "--no-first-run", "--disable-gpu", "about:blank",
], { stdio: "ignore" });

let ws;
for (let i = 0; i < 50 && !ws; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    const page = list.find((t) => t.type === "page");
    if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
  } catch {}
  await sleep(200);
}
// The socket may already be open by now, so check before waiting for the event.
await new Promise((r) => (ws.readyState === 1 ? r() : ws.addEventListener("open", r)));
let nextId = 1;
const pending = new Map();
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
};
const send = (method, params = {}) => new Promise((resolve) => {
  const id = nextId++; pending.set(id, resolve); ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) =>
  (await send("Runtime.evaluate", { expression, returnByValue: true })).result?.result?.value;

await send("Page.enable");
// the designed 1280-wide layout, cropped to 1280x672 and scaled by 0.9375 gives exactly 1200x630
await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
await send("Emulation.setScrollbarsHidden", { hidden: true });
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
await send("Page.navigate", { url: BASE });
for (let i = 0; i < 100; i++) {
  if (await evaluate("!!document.getElementById('chart') && !document.getElementById('chart').hidden")) break;
  await sleep(120);
}
await sleep(1900); // let the entrance animation finish
const shot = await send("Page.captureScreenshot", {
  format: "png", clip: { x: 0, y: 64, width: 1280, height: 672, scale: 0.9375 },
});
writeFileSync(OUT, Buffer.from(shot.result.data, "base64"));
console.log("wrote", OUT);
ws.close();
chrome.kill();
process.exit(0);

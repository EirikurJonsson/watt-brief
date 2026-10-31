import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Usage: node scripts/ui_check.mjs [baseUrl] [screenshotDir]
// Needs chromium and a running server (uv run python -m watt_brief.serve).
// The API is mocked inside the browser, so this spends nothing and is deterministic.
const BASE = process.argv[2] || "http://127.0.0.1:8000/";
const OUT = process.argv[3] || ".";
const PORT = 9333;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn("chromium", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "wb-chrome-"))}`,
  "--no-first-run", "--disable-gpu", "about:blank",
], { stdio: "ignore" });

async function targetWs() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("chromium did not start");
}

const ws = new WebSocket(await targetWs());
await new Promise((r) => (ws.onopen = r));
let nextId = 1;
const pending = new Map();
const problems = [];
const requestHandlers = [];

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
    return;
  }
  if (msg.method === "Log.entryAdded") {
    const { level, text, url } = msg.params.entry;
    if (level === "error" || level === "warning") problems.push(`${level}: ${text} ${url || ""}`);
  }
  if (msg.method === "Runtime.exceptionThrown") {
    problems.push("exception: " + msg.params.exceptionDetails.text);
  }
  if (msg.method === "Fetch.requestPaused") {
    const handler = requestHandlers[0];
    if (handler) handler(msg.params);
    else send("Fetch.continueRequest", { requestId: msg.params.requestId });
  }
};
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return r.result?.result?.value;
};
async function waitFor(expression, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(expression)) return true;
    await sleep(150);
  }
  return false;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.result.data, "base64"));
  console.log("screenshot:", name);
}
async function viewport(width, height, scheme) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
}
async function load() {
  await send("Page.navigate", { url: BASE });
  await waitFor("document.readyState === 'complete'");
  await sleep(400);
}

await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");

// 1. first paint, desktop light and dark, phone dark
await viewport(1000, 800, "light");
await load();
console.log("banner:", await evaluate("document.getElementById('data-banner').textContent"));
await shot("ui_1_light.png");
await viewport(1000, 800, "dark");
await shot("ui_2_dark.png");

// 2. empty submit
await evaluate("document.getElementById('submit').click()");
console.log("empty submit error:", await evaluate("document.getElementById('error').textContent"));

// 3. a question answered by a mocked API
await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/brief" }] });
const fulfill = (status, body) => (p) =>
  send("Fetch.fulfillRequest", {
    requestId: p.requestId, responseCode: status,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }],
    body: Buffer.from(JSON.stringify(body)).toString("base64"),
  });
requestHandlers[0] = fulfill(200, {
  recommendation: "Run the heat pump from 10:00 to 13:00 UTC, the cheapest 3-hour window.",
  reasoning: "The window averages 3.0 EUR/MWh against a day mean of 69.25 EUR/MWh.",
  caveats: ["All times are UTC.", "Day-ahead prices only."],
  zone: "DE_LU", window_hours: 3, data_source: "synthetic", request_id: "abc123",
});
await evaluate("document.querySelector('.chip').click()");
await evaluate("document.getElementById('submit').click()");
const ok = await waitFor("!document.getElementById('result').hidden");
console.log("result shown:", ok);
console.log("rec:", await evaluate("document.getElementById('rec').textContent"));
console.log("focus moved to result:", await evaluate("document.activeElement.id"));
await shot("ui_3_result_dark.png");
await viewport(390, 800, "light");
await shot("ui_4_result_phone_light.png");

// 4. server-side rejection shown as a message, and the old result is cleared
requestHandlers[0] = fulfill(422, { error: "I only answer questions about electricity prices and when to use power." });
await evaluate("document.getElementById('question').value = 'write a poem about cats'");
await evaluate("document.getElementById('submit').click()");
await waitFor("!document.getElementById('error').hidden");
console.log("rejection shown:", await evaluate("document.getElementById('error').textContent"));
console.log("result hidden after error:", await evaluate("document.getElementById('result').hidden"));

// 4b. rate limit message
requestHandlers[0] = fulfill(429, { error: "Too many requests. Try again later." });
await evaluate("document.getElementById('submit').click()");
await waitFor("document.getElementById('error').textContent.startsWith('Too many')");
console.log("rate limit shown:", await evaluate("document.getElementById('error').textContent"));

// 5. hostile server response must render as inert text
const evil = {
  recommendation: "<img src=x onerror=\"window.__xss=1\">REC",
  reasoning: "<script>window.__xss=2</script>REASON",
  caveats: ["<b>bold</b>", "<a href='javascript:window.__xss=3'>link</a>"],
  zone: "<i>DE_LU</i>", window_hours: 3, data_source: "synthetic", request_id: "<u>id</u>",
};
requestHandlers[0] = fulfill(200, evil);
await evaluate("document.getElementById('question').value = 'power price tomorrow?'");
await evaluate("document.getElementById('submit').click()");
await waitFor("!document.getElementById('result').hidden");
console.log("injected elements inside result:", await evaluate("document.querySelectorAll('#result img, #result script, #result b, #result a, #result i, #result u').length"));
console.log("xss flag:", await evaluate("window.__xss === undefined ? 'not triggered' : 'TRIGGERED ' + window.__xss"));
console.log("rec shown literally:", await evaluate("document.getElementById('rec').textContent"));
await shot("ui_5_hostile_response.png");

// the mocked 422 and 429 responses legitimately show up as network errors in the console
const real = problems.filter((p) => !/status of (422|429)/.test(p));
console.log("\nconsole problems:", real.length ? real : "none");
const injected = await evaluate("document.querySelectorAll('#result img, #result script, #result b, #result a, #result i, #result u').length");
const triggered = await evaluate("window.__xss !== undefined");
const failed = real.length > 0 || injected > 0 || triggered;
console.log(failed ? "UI CHECK FAILED" : "UI CHECK PASSED");
ws.close();
chrome.kill();
process.exit(failed ? 1 : 0);

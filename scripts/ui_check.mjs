// Usage: node scripts/ui_check.mjs [baseUrl] [screenshotDir]
// Needs chromium and a running server (uv run python -m watt_brief.serve).
// Prices come from the server. The brief API is mocked inside the browser, so this spends
// nothing on the model and is deterministic.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// UI_REAL=1 sends the first question to the real model (costs a fraction of a cent).
const REAL = process.env.UI_REAL === "1";
const BASE = process.argv[2] || "http://127.0.0.1:8000/";
const OUT = process.argv[3] || ".";
const PORT = 9333;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// CHROME_BIN picks the browser (CI uses google-chrome); CI=true adds --no-sandbox, which the
// hosted runners need because they run it inside a container-like user namespace.
const chrome = spawn(process.env.CHROME_BIN || "chromium", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  ...(process.env.CI ? ["--no-sandbox"] : []),
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "wb-chrome-"))}`,
  "--no-first-run", "--disable-gpu", "about:blank",
], { stdio: "ignore" });

async function targetWs() {
  for (let i = 0; i < 150; i++) { // 30 s: a cold CI runner can be slow to start Chrome
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
let apiHandler = null;

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
    problems.push("exception: " + JSON.stringify(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
  }
  if (msg.method === "Fetch.requestPaused") {
    const { requestId, request } = msg.params;
    if (request.url.endsWith("/api/brief") && apiHandler) apiHandler(requestId);
    else send("Fetch.continueRequest", { requestId });
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
async function waitFor(expression, ms = 20000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(expression)) return true;
    await sleep(120);
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
  await waitFor("!document.getElementById('chart').hidden");
  await sleep(1900); // let the one entrance animation finish
}
const check = (name, ok, detail = "") => {
  console.log((ok ? "ok   " : "FAIL ") + name + (detail ? "  " + detail : ""));
  if (!ok) problems.push("check failed: " + name);
};
const mouse = (type, x, y) => send("Input.dispatchMouseEvent", { type, x, y });
const scrollTo = (selector) => evaluate(`document.querySelector('${selector}').scrollIntoView({block:'center'})`);

await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");
await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/brief" }] });

// 1. first paint
await viewport(1280, 900, "light");
await load();
const fold = await evaluate("document.getElementById('plot').getBoundingClientRect().bottom <= window.innerHeight");
check("whole chart is above the fold on a 1280x900 screen", fold);
check("headline states the window", /^Power is cheapest between \d\d:\d\d and \d\d:\d\d UTC\.$/.test(await evaluate("document.getElementById('answer').textContent")));
check("context says the data is synthetic", (await evaluate("document.getElementById('context').textContent")).includes("Synthetic demo data"));
const bars = await evaluate("document.querySelectorAll('#area .bar').length");
check("chart has a column per hour", bars >= 23, `(${bars} bars)`);
check("cheap and pricey columns are marked", (await evaluate("document.querySelectorAll('.bar.is-cheap').length")) === 3 && (await evaluate("document.querySelectorAll('.bar.is-pricey').length")) === 3);
check("negative price column hangs below zero", (await evaluate("document.querySelectorAll('.bar.is-below').length")) === 1);
check("both brackets are labelled", (await evaluate("document.querySelectorAll('.bracket-label:not([hidden])').length")) === 2);
await shot("ui_1_hero_light.png");

// 2. hover shows a tooltip with the value first
await scrollTo("#plot");
await sleep(200);
const rect = JSON.parse(await evaluate("JSON.stringify(document.getElementById('area').getBoundingClientRect())"));
const x = rect.x + rect.width * (13.5 / 24);
await mouse("mouseMoved", x, rect.y + rect.height * 0.6);
await sleep(150);
const tipText = await evaluate("document.querySelector('.tip').textContent");
check("tooltip shows value and time", tipText.includes("EUR/MWh") && tipText.includes("UTC"), JSON.stringify(tipText.slice(0, 60)));
check("tooltip names the window", tipText.includes("cheapest window"));
await shot("ui_2_hover_light.png");
await mouse("mouseMoved", 5, 5);

// 3. keyboard
await evaluate("document.getElementById('plot').focus()");
await sleep(100);
const start = await evaluate("document.getElementById('live').textContent");
await send("Input.dispatchKeyEvent", { type: "keyDown", key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 });
await send("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 });
await sleep(100);
const next = await evaluate("document.getElementById('live').textContent");
check("arrow keys move through the hours and announce them", start !== next && next.includes("EUR/MWh"), JSON.stringify(next));
await evaluate("document.activeElement.blur()");

// 4. table view
await evaluate("document.getElementById('view-toggle').click()");
await scrollTo("#table-wrap");
check("table view lists every hour", (await evaluate("document.querySelectorAll('#table-body tr').length")) === (await evaluate("document.querySelectorAll('.slot').length")));
check("table hides the chart", await evaluate("document.getElementById('plot').hidden"));
await shot("ui_6_table.png");
await evaluate("document.getElementById('view-toggle').click()");

// 5. dark and phone
await viewport(1280, 900, "dark");
await sleep(300);
await shot("ui_3_hero_dark.png");
await viewport(390, 844, "light");
await load();
await shot("ui_4_hero_phone.png");
check("no horizontal scroll on a phone", await evaluate("document.documentElement.scrollWidth <= window.innerWidth"));
const overlap = await evaluate(`(() => {
  const r = [...document.querySelectorAll('.bracket-label')].filter(l => !l.hidden).map(l => l.getBoundingClientRect());
  return r.some((a, i) => r.some((b, j) => i < j && a.left < b.right && b.left < a.right));
})()`);
check("bracket labels do not overlap on a phone", overlap === false);
check("both bracket labels still visible on a phone", (await evaluate("document.querySelectorAll('.bracket-label:not([hidden])').length")) === 2);
const above = await evaluate("document.getElementById('plot').getBoundingClientRect().bottom <= window.innerHeight");
check("whole chart fits on a phone screen", above, "(plot bottom vs viewport)");

// 6. ask, with the API mocked
await viewport(1280, 900, "dark");
await load();
const fulfill = (status, body) => (requestId) =>
  send("Fetch.fulfillRequest", {
    requestId, responseCode: status,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }],
    body: Buffer.from(JSON.stringify(body)).toString("base64"),
  });
const prices = await (await fetch(new URL("/api/prices?hours=2", BASE))).json();
apiHandler = REAL ? null : fulfill(200, {
  recommendation: "Run the heat pump from 11:00 to 13:00 UTC, the cheapest 2 hours.",
  reasoning: "That window averages 0.5 EUR/MWh against a day mean of 69.25 EUR/MWh.",
  caveats: ["All times are UTC.", "Day-ahead prices only."],
  zone: "DE_LU", window_hours: 2, data_source: "synthetic", request_id: "abc123", chart: prices,
});
await evaluate("document.querySelector('.chip').click()");
await evaluate("document.getElementById('submit').click()");
check("result appears", await waitFor("!document.getElementById('result').hidden", 90000));
check("focus moves to the result", (await evaluate("document.activeElement.id")) === "result");
check("chart follows the brief's window", REAL ? /^Cheapest \d hours?$/.test(await evaluate("document.getElementById('key-cheap').textContent")) : (await evaluate("document.getElementById('key-cheap').textContent")) === "Cheapest 2 hours");
await scrollTo("#result");
await sleep(600); // let the result finish its short fade-in
await shot("ui_5_result_dark.png");

apiHandler = fulfill(422, { error: "I only answer questions about electricity prices and when to use power." });
await evaluate("document.getElementById('question').value = 'write a poem about cats'");
await evaluate("document.getElementById('submit').click()");
await waitFor("!document.getElementById('error').hidden");
check("rejection shown as a message", (await evaluate("document.getElementById('error').textContent")).startsWith("I only answer"));
check("old result is cleared", await evaluate("document.getElementById('result').hidden"));
await evaluate("document.getElementById('question').value = ''");
await evaluate("document.getElementById('submit').click()");
check("empty question explained", (await evaluate("document.getElementById('error').textContent")) === "Type a question first.");

apiHandler = fulfill(429, { error: "Too many requests. Try again later." });
await evaluate("document.getElementById('question').value = 'power price?'");
await evaluate("document.getElementById('submit').click()");
await waitFor("document.getElementById('error').textContent.startsWith('Too many')");
check("rate limit shown", true);

// 7. hostile response must render as inert text
const evil = {
  recommendation: "<img src=x onerror=\"window.__xss=1\">REC",
  reasoning: "<script>window.__xss=2</script>REASON",
  caveats: ["<b>bold</b>", "<a href='javascript:window.__xss=3'>link</a>"],
  zone: "<i>DE_LU</i>", window_hours: 3, data_source: "synthetic", request_id: "<u>id</u>",
  chart: { ...prices, zone_name: "<img src=x onerror=\"window.__xss=4\">", window_hours: 2 },
};
apiHandler = fulfill(200, evil);
await evaluate("document.getElementById('question').value = 'power price tomorrow?'");
await evaluate("document.getElementById('submit').click()");
await waitFor("!document.getElementById('result').hidden");
const injected = await evaluate("document.querySelectorAll('main img, main script, #result b, #result a, #result i, #result u, #context img').length");
check("hostile response creates no elements", injected === 0, `(${injected})`);
check("hostile response runs no script", (await evaluate("window.__xss === undefined")));

// 8. the page itself
const head = await fetch(BASE);
const csp = head.headers.get("content-security-policy") || "";
check("page sets a strict CSP", csp.includes("default-src 'self'") && !csp.includes("unsafe-inline") && !csp.includes("unsafe-eval"), csp);
const real = problems.filter((p) => !/status of (422|429)/.test(p));
console.log("\nconsole problems:", real.length ? real : "none");
const failed = real.length > 0;
console.log(failed ? "UI CHECK FAILED" : "UI CHECK PASSED");
ws.close();
chrome.kill();
process.exit(failed ? 1 : 0);

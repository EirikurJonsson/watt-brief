"use strict";

// Everything from the server is shown with textContent, never as HTML.
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("ask");
  const box = $("question");
  const submit = $("submit");
  const errorEl = $("error");
  const result = $("result");
  const MAX = Number(box.getAttribute("maxlength")) || 500;
  const TIMEOUT_MS = 60000;

  function updateCount() {
    $("count").textContent = box.value.length + " / " + MAX;
  }

  function showError(message) {
    result.hidden = true;
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function showResult(data) {
    errorEl.hidden = true;
    $("rec").textContent = data.recommendation;
    $("reason").textContent = data.reasoning;

    const list = $("caveats");
    list.replaceChildren();
    for (const caveat of data.caveats) {
      const item = document.createElement("li");
      item.textContent = caveat;
      list.appendChild(item);
    }

    const source = data.data_source === "synthetic" ? "synthetic demo data" : "ENTSO-E day-ahead";
    $("meta").textContent =
      data.zone + " · " + data.window_hours + "-hour window · " + source +
      " · times in UTC · ref " + data.request_id;

    result.hidden = false;
    result.focus();
  }

  async function ask(question) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const response = await fetch("/api/brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_) {
        // not JSON: fall through to the generic message
      }
      if (response.ok && body) {
        showResult(body);
      } else if (response.status === 429) {
        showError((body && body.error) || "Too many requests. Try again later.");
      } else {
        showError((body && body.error) || "Something went wrong. Try again later.");
      }
    } catch (_) {
      showError("Could not reach the service. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = box.value.trim();
    if (!question) {
      showError("Type a question first.");
      box.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = "Thinking…";
    await ask(question);
    submit.disabled = false;
    submit.textContent = "Get brief";
  });

  box.addEventListener("input", updateCount);

  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      box.value = chip.textContent;
      updateCount();
      box.focus();
    });
  }

  async function loadBanner() {
    try {
      const response = await fetch("/healthz");
      const health = await response.json();
      if (health.data_source === "synthetic") {
        const banner = $("data-banner");
        banner.textContent =
          "Demo: this service is running on synthetic price data, not real market data.";
        banner.hidden = false;
      }
    } catch (_) {
      // the banner is a courtesy; the form still works
    }
  }

  updateCount();
  loadBanner();
})();

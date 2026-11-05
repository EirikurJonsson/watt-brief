"use strict";

// Everything that comes from the server is written with textContent, never as HTML.
(() => {
  const $ = (id) => document.getElementById(id);

  // ---------- formatting ----------

  const MINUS = "−";
  const t = I18N.t;
  // Number and time formats follow the chosen language; setFormats() rebuilds them on a change.
  let numberFormat, kwhFormat, localTime, zoneFormat, rateFormat;
  let priceFormat;
  function setFormats() {
    const locale = I18N.locale;
    numberFormat = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    // Per-kWh prices are small, so they need more decimals than per-MWh ones.
    kwhFormat = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    rateFormat = new Intl.NumberFormat(locale, { maximumFractionDigits: 5 });
    localTime = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hour12: false });
    zoneFormat = new Intl.DateTimeFormat(locale, { timeZoneName: "short" });
    priceFormat = chart && chart.unit === "kWh" ? kwhFormat : numberFormat;
  }
  const fmt = (value) => priceFormat.format(value).replace("-", MINUS);
  const pad = (n) => String(n).padStart(2, "0");

  const utcHM = (d) => pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  // Danish writes 10.00; the page shows every time as 10:00 so UTC and local times match.
  const localHM = (d) => localTime.format(d).replace(".", ":");
  const sameAsUtc = (d) => localHM(d) === utcHM(d);
  const zoneName = (d) => {
    const part = zoneFormat.formatToParts(d).find((p) => p.type === "timeZoneName");
    return part ? part.value : "";
  };
  const upperFirst = (text) => text.charAt(0).toUpperCase() + text.slice(1);
  const hoursLabel = (n) => I18N.hours(n);
  const perWords = (c) => c.price_label.replace("/", t("per"));
  const zoneName_ = (c) => I18N.zone(c.zone, 1) || c.zone_name;
  // Which prices these are, and where any conversion came from. Shown on every render.
  const priceBasis = (c) => {
    const words = perWords(c);
    if (c.fx) return t("basis_fx", { words, rate: rateFormat.format(c.fx.rate) });
    return c.unit === "kWh" ? t("basis_kwh", { words }) : words;
  };

  // ---------- state ----------

  let chart = null; // the payload from the server
  let pts = []; // [{ iso, t, price }]
  let scale = null; // { lo, hi, ticks }
  let windows = null; // { cheap: [from, to), pricey: [from, to) } as slot indexes
  let slots = [];
  let active = -1;
  let tip = null;

  const area = $("area");
  const plot = $("plot");

  // ---------- scale ----------

  function niceStep(range) {
    const raw = range / 4;
    const power = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / power;
    const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return nice * power;
  }

  function makeScale(prices) {
    const min = Math.min(0, ...prices);
    const max = Math.max(0, ...prices);
    const step = niceStep(max - min || 1);
    const half = step / 2;
    const hi = Math.max(step, Math.ceil((max * 1.02) / half) * half);
    // a little room under zero when prices go negative, without a whole empty tick band
    const lo = min < 0 ? min - 0.05 * (hi - min) : 0;
    const ticks = [];
    for (let k = Math.ceil(lo / step); k * step <= hi + 1e-9; k++) {
      ticks.push(Number((k * step).toPrecision(12)));
    }
    return { lo, hi, ticks };
  }

  const pct = (value) => ((value - scale.lo) / (scale.hi - scale.lo)) * 100;

  // ---------- chart ----------

  function derive(payload) {
    chart = payload;
    priceFormat = payload.unit === "kWh" ? kwhFormat : numberFormat;
    pts = payload.points.map(([iso, price]) => ({ iso, t: new Date(iso), price }));
    scale = makeScale(pts.map((p) => p.price));
    const per = (payload.window_hours * 60) / payload.resolution_minutes;
    const start = (iso) => pts.findIndex((p) => p.iso === iso);
    const cheap = start(payload.cheapest_window.start);
    const pricey = start(payload.priciest_window.start);
    windows = {
      cheap: cheap < 0 ? null : [cheap, cheap + per],
      pricey: pricey < 0 ? null : [pricey, pricey + per],
    };
  }

  const windowOf = (i) => {
    if (windows.cheap && i >= windows.cheap[0] && i < windows.cheap[1]) return "cheap";
    if (windows.pricey && i >= windows.pricey[0] && i < windows.pricey[1]) return "pricey";
    return null;
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function renderAxes() {
    const yaxis = $("yaxis");
    const xaxis = $("xaxis");
    yaxis.replaceChildren();
    xaxis.replaceChildren();

    for (const tick of scale.ticks) {
      const line = el("div", tick === 0 ? "grid-line is-zero" : "grid-line");
      line.style.bottom = pct(tick) + "%";
      area.appendChild(line);

      const label = el("span", "y-label", String(tick).replace("-", MINUS));
      label.style.bottom = pct(tick) + "%";
      yaxis.appendChild(label);
    }

    const n = pts.length;
    pts.forEach((p, i) => {
      if (p.t.getUTCMinutes() !== 0 || p.t.getUTCHours() % 3 !== 0) return;
      const label = el("span", "x-label", utcHM(p.t));
      label.style.left = (i / n) * 100 + "%";
      if (p.t.getUTCHours() === 0) {
        const date = p.t.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          timeZone: "UTC",
        });
        label.appendChild(el("span", "x-date", date));
      }
      xaxis.appendChild(label);

      const tick = el("span", "x-tick");
      tick.style.left = (i / n) * 100 + "%";
      xaxis.appendChild(tick);
    });
  }

  function renderBars() {
    const n = pts.length;
    slots = pts.map((p, i) => {
      const slot = el("div", "slot");
      slot.style.left = (i / n) * 100 + "%";
      slot.style.width = 100 / n + "%";

      if (p.price !== 0) {
        const bar = el("div", "bar");
        const kind = windowOf(i);
        if (kind) bar.classList.add("is-" + kind);
        const span = (Math.abs(p.price) / (scale.hi - scale.lo)) * 100;
        bar.style.height = "max(2px, " + span + "%)";
        if (p.price > 0) {
          bar.style.bottom = pct(0) + "%";
        } else {
          bar.classList.add("is-below");
          bar.style.bottom = pct(p.price) + "%";
        }
        bar.style.setProperty("--i", String(i));
        slot.appendChild(bar);
      }
      area.appendChild(slot);
      return slot;
    });
  }

  function renderBrackets() {
    const host = $("brackets");
    host.replaceChildren();
    const n = pts.length;
    const labels = [];
    const add = (range, kind, text) => {
      if (!range) return;
      const bracket = el("div", "bracket is-" + kind);
      bracket.style.left = (range[0] / n) * 100 + "%";
      bracket.style.width = ((range[1] - range[0]) / n) * 100 + "%";
      const label = el("span", "bracket-label", text);
      bracket.appendChild(label);
      host.appendChild(bracket);
      labels.push(label);
    };
    const narrow = window.matchMedia("(max-width: 40rem)").matches;
    const suffix = narrow ? "" : " " + hoursLabel(chart.window_hours);
    add(windows.cheap, "cheap", "Cheapest" + suffix);
    add(windows.pricey, "pricey", "Priciest" + suffix);
    fitLabels(labels, host);
  }

  // Labels sit left-aligned on their bracket. One that would run past the edge flips to the
  // right-hand end instead. If two would still collide, the second is dropped: the legend
  // below the chart names both windows anyway.
  function fitLabels(labels, host) {
    const edge = host.getBoundingClientRect().right;
    for (const label of labels) {
      label.hidden = false;
      label.classList.remove("is-right");
      if (label.getBoundingClientRect().right > edge + 0.5) label.classList.add("is-right");
    }
    if (labels.length < 2) return;
    const a = labels[0].getBoundingClientRect();
    const b = labels[1].getBoundingClientRect();
    if (a.left < b.right && b.left < a.right) labels[1].hidden = true;
  }

  function renderTable() {
    const body = $("table-body");
    body.replaceChildren();
    const first = pts[0] ? pts[0].t : new Date();
    $("local-col").textContent = t("col_local", { zone: zoneName(first) });
    $("price-col").textContent = t("col_price", { label: chart.price_label });
    $("table-caption").textContent = t("table_caption", { basis: perWords(chart) });
    pts.forEach((p, i) => {
      const row = el("tr");
      row.appendChild(el("td", "", utcHM(p.t)));
      row.appendChild(el("td", "", localHM(p.t)));
      row.appendChild(el("td", "", fmt(p.price)));
      const kind = windowOf(i);
      row.appendChild(el("td", "", kind === "cheap" ? t("note_cheap") : kind === "pricey" ? t("note_pricey") : ""));
      body.appendChild(row);
    });
  }

  function renderHero() {
    const c = chart;
    const day = pts[Math.floor(pts.length / 2)].t;
    const dayText = day.toLocaleDateString(I18N.locale, { day: "numeric", month: "long", timeZone: "UTC" });
    const source =
      c.data_source === "synthetic"
        ? t("source_synthetic")
        : c.fetched_at
          ? t("source_real_fetched", { time: utcHM(new Date(c.fetched_at)) })
          : t("source_real");
    let versus = "";
    const prev = c.previous_day;
    if (prev && prev.change_pct !== null && Math.abs(prev.change_pct) >= 1) {
      versus = " " + t(prev.change_pct < 0 ? "versus_cheaper" : "versus_dearer", { pct: Math.abs(prev.change_pct) });
    }
    $("context").textContent = upperFirst(zoneName_(c)) + ", " + dayText + ". " + source + versus;

    const from = new Date(c.cheapest_window.start);
    const to = new Date(c.cheapest_window.end);
    $("answer").textContent = t("answer", { from: utcHM(from), to: utcHM(to) });

    const parts = [];
    if (!sameAsUtc(from)) {
      parts.push(t("detail_local", { from: localHM(from), to: localHM(to), zone: zoneName(from) }));
    }
    parts.push(
      t("detail_average", { avg: fmt(c.cheapest_window.avg), label: c.price_label, mean: fmt(c.mean) })
    );
    const pFrom = new Date(c.priciest_window.start);
    const pTo = new Date(c.priciest_window.end);
    parts.push(
      t("detail_avoid", { from: utcHM(pFrom), to: utcHM(pTo), avg: fmt(c.priciest_window.avg) })
    );
    $("detail").textContent = parts.join(" ");

    $("key-cheap").textContent = t("key_cheap", { hours: hoursLabel(c.window_hours) });
    $("key-pricey").textContent = t("key_pricey", { hours: hoursLabel(c.window_hours) });
    plot.setAttribute(
      "aria-label",
      t("plot_aria", {
        zone: zoneName_(c),
        hours: hoursLabel(c.window_hours),
        from: utcHM(from),
        to: utcHM(to),
      })
    );
  }

  function renderBasis() {
    const c = chart;
    $("chart-title").textContent = t("chart_title", { basis: perWords(c) });
    $("foot-note").textContent = t("foot_note", { basis: priceBasis(c) });
    $("fx-note").textContent = c.fx ? t("fx_note", { rate: rateFormat.format(c.fx.rate) }) : "";
  }

  function render(payload, animate) {
    derive(payload);
    $("chart").hidden = false; // visible first: bracket labels are measured during layout
    area.replaceChildren();
    active = -1;
    renderAxes();
    renderBars();
    tip = el("div", "tip");
    tip.hidden = true;
    area.appendChild(tip);
    renderBrackets();
    renderTable();
    renderHero();
    renderBasis();
    if (animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      area.classList.add("is-entering");
      setTimeout(() => area.classList.remove("is-entering"), 1800);
    }
  }

  // ---------- hover and keyboard ----------

  function tipText(i) {
    const p = pts[i];
    const when = utcHM(p.t) + " UTC" + (sameAsUtc(p.t) ? "" : ", " + localHM(p.t) + " " + zoneName(p.t));
    const kind = windowOf(i);
    const note = kind === "cheap" ? t("tip_cheap") : kind === "pricey" ? t("tip_pricey") : "";
    return { value: fmt(p.price) + " " + chart.price_label, when, note, kind };
  }

  function setActive(i, announce) {
    if (i === active) return;
    if (active >= 0 && slots[active]) slots[active].classList.remove("is-active");
    active = i;
    if (i < 0) {
      tip.hidden = true;
      return;
    }
    slots[i].classList.add("is-active");

    const info = tipText(i);
    tip.replaceChildren();
    tip.appendChild(el("span", "tip-value", info.value));
    tip.appendChild(el("span", "tip-time", info.when));
    if (info.note) {
      const note = el("span", "tip-note");
      note.appendChild(el("span", "tip-key is-" + info.kind));
      note.appendChild(document.createTextNode(info.note));
      tip.appendChild(note);
    }

    const n = pts.length;
    tip.classList.toggle("is-left", i < 3);
    tip.classList.toggle("is-right", i > n - 4);
    const anchor = i < 3 ? i / n : i > n - 4 ? (i + 1) / n : (i + 0.5) / n;
    tip.style.left = anchor * 100 + "%";
    tip.style.bottom = "calc(" + pct(Math.max(pts[i].price, 0)) + "% + 16px)";
    tip.hidden = false;

    if (announce) $("live").textContent = info.when + ": " + info.value + (info.note ? ". " + info.note : "");
  }

  const slotAt = (event) => {
    const rect = area.getBoundingClientRect();
    const x = Math.min(Math.max(event.clientX - rect.left, 0), rect.width - 1);
    return Math.floor((x / rect.width) * pts.length);
  };

  area.addEventListener("pointermove", (event) => setActive(slotAt(event), false));
  area.addEventListener("pointerdown", (event) => setActive(slotAt(event), false));
  area.addEventListener("pointerleave", () => {
    if (document.activeElement !== plot) setActive(-1, false);
  });

  plot.addEventListener("focus", () => {
    if (active < 0 && pts.length) setActive(windows.cheap ? windows.cheap[0] : 0, true);
  });
  plot.addEventListener("blur", () => setActive(-1, false));
  plot.addEventListener("keydown", (event) => {
    const last = pts.length - 1;
    const here = active < 0 ? 0 : active;
    const moves = {
      ArrowRight: Math.min(last, here + 1),
      ArrowLeft: Math.max(0, here - 1),
      Home: 0,
      End: last,
    };
    if (event.key === "Escape") {
      setActive(-1, false);
    } else if (event.key in moves) {
      event.preventDefault();
      setActive(moves[event.key], true);
    }
  });

  // ---------- table view ----------

  let tableMode = false;
  $("view-toggle").addEventListener("click", () => {
    tableMode = !tableMode;
    plot.hidden = tableMode;
    $("table-wrap").hidden = !tableMode;
    $("view-toggle").textContent = t(tableMode ? "show_chart" : "show_table");
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (chart) renderBrackets();
    }, 150);
  });

  // ---------- choices: country, unit, currency ----------

  const choice = { zone: null, unit: "MWh", currency: "EUR", language: "en" };
  let zones = []; // [{ code, label }] from /api/zones

  const zoneInput = $("zone-input");
  const zoneList = $("zone-list");
  let options = []; // the zones currently listed
  let highlighted = -1;

  // Names come from the page's own translations; the server's label is the fallback.
  const labelOf = (z) => I18N.zone(z.code, 0) || z.label;
  const zoneLabel = (code) => {
    const found = zones.find((z) => z.code === code);
    return found ? labelOf(found) : "";
  };

  function closeList() {
    zoneList.hidden = true;
    zoneInput.setAttribute("aria-expanded", "false");
    zoneInput.removeAttribute("aria-activedescendant");
    highlighted = -1;
  }

  function highlight(i) {
    highlighted = i;
    zoneList.querySelectorAll("li").forEach((li, n) => {
      li.setAttribute("aria-selected", n === i ? "true" : "false");
    });
    if (i >= 0) {
      zoneInput.setAttribute("aria-activedescendant", "zone-opt-" + i);
      zoneList.children[i].scrollIntoView({ block: "nearest" });
    } else {
      zoneInput.removeAttribute("aria-activedescendant");
    }
  }

  function openList(filter) {
    const needle = filter.trim().toLowerCase();
    options = zones.filter((z) => labelOf(z).toLowerCase().includes(needle));
    zoneList.replaceChildren();
    options.forEach((z, i) => {
      const li = el("li", "combo-option", labelOf(z));
      li.id = "zone-opt-" + i;
      li.setAttribute("role", "option");
      li.addEventListener("mousedown", (event) => {
        event.preventDefault(); // keep focus in the input
        pickZone(z.code);
      });
      zoneList.appendChild(li);
    });
    if (!options.length) zoneList.appendChild(el("li", "combo-empty", t("combo_empty")));
    zoneList.hidden = false;
    zoneInput.setAttribute("aria-expanded", "true");
    highlight(options.length ? 0 : -1);
  }

  function pickZone(code) {
    closeList();
    zoneInput.value = zoneLabel(code);
    if (code !== choice.zone) {
      choice.zone = code;
      loadPrices();
    }
  }

  zoneInput.addEventListener("focus", () => {
    zoneInput.select();
    openList("");
  });
  zoneInput.addEventListener("click", () => {
    if (zoneList.hidden) openList("");
  });
  zoneInput.addEventListener("input", () => openList(zoneInput.value));
  zoneInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (zoneList.hidden) openList("");
      else if (options.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        highlight((highlighted + step + options.length) % options.length);
      }
    } else if (event.key === "Enter" && !zoneList.hidden) {
      event.preventDefault();
      if (highlighted >= 0) pickZone(options[highlighted].code);
    } else if (event.key === "Escape" && !zoneList.hidden) {
      event.preventDefault();
      zoneInput.value = zoneLabel(choice.zone);
      closeList();
    }
  });
  zoneInput.addEventListener("blur", () => {
    closeList();
    if (zoneInput.value.trim() === "" && choice.zone !== null) {
      // an emptied field hands the choice back to the question
      choice.zone = null;
      loadPrices();
    }
    zoneInput.value = zoneLabel(choice.zone);
  });

  for (const radio of document.querySelectorAll('input[name="unit"], input[name="currency"]')) {
    radio.addEventListener("change", () => {
      choice[radio.name] = radio.value;
      loadPrices();
    });
  }

  // One choice drives the whole page and the language the brief is written in.
  function applyLanguage() {
    document.documentElement.lang = I18N.lang;
    document.title = t("page_title");
    const description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute("content", t("page_description"));
    for (const node of document.querySelectorAll("[data-i18n]")) {
      node.textContent = t(node.dataset.i18n);
    }
    for (const node of document.querySelectorAll("[data-i18n-attr]")) {
      for (const pair of node.dataset.i18nAttr.split(";")) {
        const [attr, key] = pair.split(":");
        node.setAttribute(attr, t(key));
      }
    }
    for (const chip of document.querySelectorAll("[data-i18n-q]")) {
      chip.dataset.q = t(chip.dataset.i18nQ);
    }
    $("view-toggle").textContent = t(tableMode ? "show_chart" : "show_table");
    if (submit.disabled) submit.textContent = t("working");
    zoneInput.value = zoneLabel(choice.zone);
    setFormats();
    updateCount();
    if (chart) render(chart, false);
  }

  function setLanguage(code, persist) {
    I18N.set(code, persist);
    choice.language = I18N.lang;
    $("language").value = I18N.lang;
    applyLanguage();
  }

  $("language").addEventListener("change", (event) => setLanguage(event.target.value, true));

  async function loadZones() {
    try {
      const response = await fetch("/api/zones");
      if (!response.ok) throw new Error("status " + response.status);
      zones = await response.json();
      zoneInput.disabled = false;
    } catch (_) {
      // the country field stays disabled; the page works without it
    }
  }

  // ---------- prices ----------

  async function loadPrices() {
    const query = new URLSearchParams({
      unit: choice.unit,
      currency: choice.currency,
      hours: String(chart ? chart.window_hours : 3),
    });
    if (choice.zone) query.set("zone", choice.zone);
    try {
      const response = await fetch("/api/prices?" + query);
      if (!response.ok) throw new Error("status " + response.status);
      render(await response.json(), true);
    } catch (_) {
      $("chart").hidden = true;
      $("context").textContent = "";
      $("answer").textContent = t("prices_unavailable");
      $("detail").textContent = t("prices_unavailable_detail");
    }
  }

  // ---------- ask ----------

  const form = $("ask");
  const box = $("question");
  const submit = $("submit");
  const errorEl = $("error");
  const result = $("result");
  const MAX = Number(box.getAttribute("maxlength")) || 500;
  const TIMEOUT_MS = 60000;

  const updateCount = () => {
    $("count").textContent = t("count", { n: box.value.length, max: MAX });
  };

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
    for (const caveat of data.caveats) list.appendChild(el("li", "", caveat));

    const source = t(data.data_source === "synthetic" ? "meta_source_synthetic" : "meta_source_real");
    const basis = t(
      data.zone_source === "selector"
        ? "meta_basis_selector"
        : data.zone_source === "question"
          ? "meta_basis_question"
          : "meta_basis_default"
    );
    const prices = data.chart ? t("meta_prices", { basis: priceBasis(data.chart) }) : "";
    $("meta").textContent = t("meta", {
      source,
      zone: I18N.zone(data.zone, 0) || data.zone,
      basis,
      hours: data.window_hours,
      unit: data.brief_unit,
      prices,
      id: data.request_id,
    });

    result.hidden = false;
    result.focus();

    // keep the chart in step with the window the brief talked about
    if (data.chart) render(data.chart, false);
  }

  // The server sends a stable code with each error; the page shows its own text for it, in the
  // chosen language, and falls back to the server's English message for a code it does not know.
  function errorText(body) {
    const code = body && body.code;
    if (code && STRINGS.en["err_" + code]) return t("err_" + code);
    return (body && body.error) || t("err_error");
  }

  async function ask(question) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const response = await fetch("/api/brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          unit: choice.unit,
          currency: choice.currency,
          language: choice.language,
          ...(choice.zone ? { zone: choice.zone } : {}),
        }),
        signal: controller.signal,
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_) {
        // not JSON: use the generic message below
      }
      if (response.ok && body) {
        showResult(body);
      } else {
        showError(errorText(body));
      }
    } catch (_) {
      showError(t("network_error"));
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = box.value.trim();
    if (!question) {
      showError(t("empty_question"));
      box.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = t("working");
    await ask(question);
    submit.disabled = false;
    submit.textContent = t("get_brief");
  });

  box.addEventListener("input", updateCount);

  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      box.value = chip.dataset.q || "";
      updateCount();
      box.focus();
    });
  }

  setLanguage(I18N.initial(), false);
  loadZones().then(() => {
    zoneInput.value = zoneLabel(choice.zone);
  });
  loadPrices();
})();

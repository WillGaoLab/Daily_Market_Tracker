/* Interactive viewer for the original Matplotlib Market Fingerprint SVG. */
(function (global) {
  "use strict";
  const instruments = [
    ["sp500", "S&P 500", false], ["nasdaq100", "Nasdaq-100 Futures", false],
    ["dow", "Dow Jones Industrial Average", false], ["vix", "VIX", true],
    ["bitcoin", "Bitcoin", false], ["gold", "Gold Futures", false],
    ["tnx", "U.S. 10-Year Treasury Yield", false], ["dxy", "U.S. Dollar Index", true],
    ["wti", "WTI Crude Oil", false],
  ];
  const percentField = (key) => `${key}_${key === "bitcoin" ? "change_pct" : "gap_pct"}`;
  const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
    && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  const numeric = (value) => value != null && String(value).trim() !== "" && value !== "NA" && Number.isFinite(Number(value));
  const pct = (value, digits = 3) => numeric(value) ? `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(digits)}%` : "Unavailable";
  const number = (value) => numeric(value) ? Number(value).toLocaleString("en-US", { maximumFractionDigits: 6 }) : "Unavailable";
  const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

  function parseCsv(text) {
    const records = []; let fields = []; let field = ""; let quoted = false;
    text = text.replace(/^\uFEFF/, "");
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (char === '"') {
        if (quoted && text[i + 1] === '"') { field += '"'; i += 1; }
        else quoted = !quoted;
      } else if (char === "," && !quoted) { fields.push(field); field = ""; }
      else if ((char === "\n" || char === "\r") && !quoted) {
        if (char === "\r" && text[i + 1] === "\n") i += 1;
        fields.push(field); if (fields.some((value) => value !== "")) records.push(fields);
        fields = []; field = "";
      } else field += char;
    }
    if (quoted) throw new Error("Unterminated CSV field.");
    fields.push(field); if (fields.some((value) => value !== "")) records.push(fields);
    const headers = records.shift() || [];
    const required = ["date", "source", ...instruments.flatMap(([key]) => key === "bitcoin"
      ? ["bitcoin_open", "bitcoin_current", "bitcoin_change", "bitcoin_change_pct"]
      : ["previous_close", "open", "gap", "gap_pct"].map((suffix) => `${key}_${suffix}`))];
    if (new Set(headers).size !== headers.length || !required.every((key) => headers.includes(key))) throw new Error("Tracker history is missing required columns.");
    const dates = new Set();
    return records.map((values) => {
      if (values.length !== headers.length) throw new Error("Tracker row has an unexpected number of columns.");
      const row = Object.fromEntries(headers.map((key, i) => [key, values[i]]));
      if (!validDate(row.date) || !row.source.trim() || dates.has(row.date)
        || !required.slice(2).every((key) => row[key] === "NA" || numeric(row[key]))) throw new Error("Tracker history has an invalid or duplicate record.");
      dates.add(row.date); return row;
    }).sort((a, b) => a.date.localeCompare(b.date));
  }

  function measurement(row, key) {
    const [, label, reverse] = instruments.find(([item]) => item === key);
    const bitcoin = key === "bitcoin";
    const raw = row[percentField(key)];
    return { key, label, reverse, raw, adjusted: numeric(raw) ? Number(raw) * (reverse ? -1 : 1) : "NA",
      baseline: row[`${key}_${bitcoin ? "open" : "previous_close"}`],
      current: row[`${key}_${bitcoin ? "current" : "open"}`],
      baselineLabel: bitcoin ? "00:00 UTC open" : "Previous close",
      currentLabel: bitcoin ? "Collection-time price" : "Daily open" };
  }

  function validateSvgValues(date, values, row) {
    if (date !== row.date || !Array.isArray(values) || values.length !== 9
      || instruments.some(([key], index) => !numeric(row[percentField(key)])
        || !Number.isFinite(values[index]) || Math.abs(values[index] - Number(row[percentField(key)])) > 1e-9)) {
      throw new Error("The figure does not match the selected Tracker record.");
    }
  }

  function readSvg(text, row) {
    const document = new DOMParser().parseFromString(text, "image/svg+xml");
    const svg = document.documentElement;
    if (svg.localName !== "svg" || document.querySelector("parsererror")) throw new Error("The interactive figure is invalid.");
    validateSvgValues(svg.dataset.fingerprintDate, JSON.parse(svg.dataset.fingerprintValues || "null"), row);
    const tags = new Set(["svg", "g", "defs", "clipPath", "path", "rect", "circle", "line", "polyline", "polygon", "use", "image", "text", "tspan", "title", "desc"]);
    for (const element of [svg, ...svg.querySelectorAll("*")]) {
      if (!tags.has(element.localName)) { element.remove(); continue; }
      for (const attr of [...element.attributes]) {
        if (/^on/i.test(attr.name) || /(?:javascript:|@import|expression\()/i.test(attr.value)
          || (/url\(/i.test(attr.value) && !/^url\(#[\w-]+\)$/.test(attr.value))
          || (attr.localName === "href" && !/^#[\w-]+$/.test(attr.value) && !(element.localName === "image" && /^data:image\/png;base64,[\sA-Za-z0-9+/=]+$/.test(attr.value)))) element.removeAttributeNode(attr);
      }
    }
    // Matplotlib's one global style rule is reproduced locally, avoiding SVG CSS injection.
    svg.style.strokeLinejoin = "round"; svg.style.strokeLinecap = "butt";
    if (svg.querySelectorAll("[data-indicator]").length !== 18) throw new Error("Interactive targets are missing.");
    return svg;
  }

  function save(text, filename, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function mount(root, options) {
    const rows = [...options.rows].sort((a, b) => a.date.localeCompare(b.date));
    if (!rows.length) throw new Error("No Tracker records are available.");
    root.classList.add("fingerprint-explorer");
    root.innerHTML = `<div class="fp-toolbar"><label class="fp-date">Fingerprint date <select aria-label="Fingerprint date"></select></label><button type="button" data-action="previous" aria-label="Previous observation">←</button><button type="button" data-action="next" aria-label="Next observation">→</button><button type="button" data-action="latest">Latest</button><span class="fp-history-range"></span></div>
      <div class="fp-toolbar fp-views" role="group" aria-label="Chart view"><button type="button" data-view="full">Full figure</button><button type="button" data-view="radar">Radar</button><button type="button" data-view="heatmap">Heatmap</button><button type="button" data-action="zoom-in" aria-label="Zoom in">+</button><button type="button" data-action="zoom-out" aria-label="Zoom out">−</button><button type="button" data-action="reset">Reset view</button><button type="button" data-action="download">Download SVG</button></div>
      <p class="fp-state" role="status" aria-live="polite"></p><div class="fp-viewport" aria-label="Interactive fingerprint"></div>
      <div class="fp-detail" aria-live="polite">Hover, focus, or tap a radar point or heatmap tile for its raw values. Use + / − to zoom, then drag to pan.</div>
      <details class="fp-values"><summary>View raw values for <span></span></summary><div class="fp-table-wrap"><table><thead><tr><th>Indicator</th><th>Baseline</th><th>Open / current</th><th>Raw change</th><th>Adjusted</th></tr></thead><tbody></tbody></table></div><p>Eight instruments: previous close → daily open. Bitcoin: 00:00 UTC open → collection-time price. Treasury-yield changes are relative percentages, not basis points. VIX and DXY are reversed for position/color only.</p></details>`;
    const select = root.querySelector("select");
    select.innerHTML = rows.map((row) => `<option value="${escape(row.date)}">${escape(row.date)}</option>`).join("");
    root.querySelector(".fp-history-range").textContent = `${rows[0].date} – ${rows.at(-1).date}`;
    if (options.selectable === false) root.querySelector(".fp-toolbar").hidden = true;
    const viewport = root.querySelector(".fp-viewport"), state = root.querySelector(".fp-state"), detail = root.querySelector(".fp-detail");
    let selected = null, svg = null, fullBox = null, baseBox = null, box = null, request = 0, downloadedSvg = "";
    let view = window.matchMedia("(max-width: 600px)").matches ? "radar" : "full";
    const setBox = () => { if (svg) { svg.setAttribute("viewBox", box.join(" ")); svg.style.touchAction = box[2] < fullBox[2] ? "none" : "pan-y"; } };
    function setView(next) {
      view = next;
      root.querySelectorAll("[data-view]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.view === view)));
      if (!svg) return;
      svg.querySelectorAll('#figure_1 > g').forEach((group) => {
        const id = group.id;
        group.style.display = ((id === "axes_1" && view === "heatmap")
          || ((id === "axes_2" || id === "axes_3") && view === "radar")
          || (id.startsWith("text_") && view !== "full")) ? "none" : "";
      });
      svg.querySelectorAll('[data-indicator]').forEach((target) => {
        target.style.display = (view === "radar" && target.localName === "rect")
          || (view === "heatmap" && target.localName === "circle") ? "none" : "";
      });
      baseBox = view === "full" ? fullBox : svg.getAttribute(`data-${view}-view`).split(/\s+/).map(Number);
      box = [...baseBox]; setBox();
    }
    function zoom(factor) {
      if (!svg) return;
      const width = Math.min(fullBox[2] * 1.25, Math.max(fullBox[2] / 8, box[2] * factor));
      const height = box[3] * width / box[2];
      box = [box[0] + (box[2] - width) / 2, box[1] + (box[3] - height) / 2, width, height]; setBox();
    }
    function showDetails(key) {
      const item = measurement(selected, key);
      root.querySelectorAll("[data-indicator]").forEach((target) => target.classList.toggle("fp-selected", target.dataset.indicator === key));
      detail.innerHTML = `<strong>${escape(item.label)} · ${escape(selected.date)}</strong><br>${escape(item.baselineLabel)}: ${number(item.baseline)} → ${escape(item.currentLabel)}: ${number(item.current)} · Raw change: <strong>${pct(item.raw)}</strong> · Direction-adjusted: ${pct(item.adjusted)}${item.reverse ? " (reversed for chart position/color)" : ""}.<br><span>Source: ${escape(selected.source)}${key === "tnx" ? ". Relative yield change; not basis points." : "."}</span>`;
    }
    async function show(date) {
      const token = ++request;
      selected = rows.find((row) => row.date === date) || rows.at(-1); select.value = selected.date;
      const row = selected;
      const index = rows.indexOf(row);
      root.querySelector('[data-action="previous"]').disabled = index === 0;
      root.querySelector('[data-action="next"]').disabled = index === rows.length - 1;
      root.querySelector('[data-action="download"]').disabled = true;
      root.dataset.selectedDate = row.date;
      root.querySelector(".fp-values summary span").textContent = row.date;
      root.querySelector("tbody").innerHTML = instruments.map(([key]) => { const item = measurement(row, key); return `<tr><th scope="row">${escape(item.label)}</th><td>${number(item.baseline)}</td><td>${number(item.current)}</td><td>${pct(item.raw)}</td><td>${pct(item.adjusted)}</td></tr>`; }).join("");
      viewport.replaceChildren(); svg = null;
      detail.textContent = "Hover, focus, or tap a radar point or heatmap tile for its raw values. Use + / − to zoom, then drag to pan.";
      state.textContent = `Loading fingerprint for ${row.date}…`;
      try {
        if (instruments.some(([key]) => !numeric(row[percentField(key)]))) throw new Error("This migrated record has unavailable values, so a complete nine-indicator fingerprint cannot be drawn. The recorded values remain available below.");
        const text = await options.loadSvg(row.date);
        if (token !== request) return;
        svg = readSvg(text, row); downloadedSvg = new XMLSerializer().serializeToString(svg);
        fullBox = svg.getAttribute("viewBox").split(/\s+/).map(Number);
        viewport.replaceChildren(svg); setView(view);
        state.textContent = `Showing ${row.date} · Opening/reference changes`;
        root.querySelector('[data-action="download"]').disabled = false;
        svg.querySelectorAll("[data-indicator]").forEach((target) => {
          target.addEventListener("pointerenter", () => showDetails(target.dataset.indicator));
          target.addEventListener("focus", () => showDetails(target.dataset.indicator));
          target.addEventListener("click", () => showDetails(target.dataset.indicator));
          target.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showDetails(target.dataset.indicator); } });
        });
        let drag = null;
        svg.addEventListener("pointerdown", (event) => { if (event.button !== 0) return; drag = { x: event.clientX, y: event.clientY, box: [...box] }; svg.setPointerCapture(event.pointerId); });
        svg.addEventListener("pointermove", (event) => {
          if (!drag) return;
          // Convert screen coordinates through the SVG transform, including aspect-ratio letterboxing.
          const scale = svg.getScreenCTM().a;
          box = [drag.box[0] - (event.clientX - drag.x) / scale, drag.box[1] - (event.clientY - drag.y) / scale, ...drag.box.slice(2)]; setBox();
        });
        ["pointerup", "pointercancel", "lostpointercapture"].forEach((event) => svg.addEventListener(event, () => { drag = null; }));
      } catch (error) {
        if (token !== request) return;
        state.textContent = `Fingerprint unavailable for ${row.date}. ${error.message} Use the raw values below.`;
        viewport.replaceChildren(); svg = null;
      }
    }
    select.addEventListener("change", () => show(select.value));
    root.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    root.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      if (action === "latest") show(rows.at(-1).date);
      if (action === "previous" || action === "next") show(rows[rows.indexOf(selected) + (action === "previous" ? -1 : 1)].date);
      if (action === "zoom-in") zoom(0.8);
      if (action === "zoom-out") zoom(1.25);
      if (action === "reset") setView(window.matchMedia("(max-width: 600px)").matches ? "radar" : "full");
      if (action === "download" && svg) save(downloadedSvg, `market-fingerprint-${selected.date}.svg`, "image/svg+xml");
    }));
    const ready = show(options.initialDate);
    return { ready, show };
  }
  const api = { parseCsv, measurement, validateSvgValues, mount };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.FingerprintExplorer = api;
})(typeof window !== "undefined" ? window : globalThis);

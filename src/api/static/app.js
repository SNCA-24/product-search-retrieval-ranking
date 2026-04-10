const config = window.ESCI_UI_CONFIG;
const initialState = JSON.parse(document.getElementById("initial-state").textContent);

const form = document.getElementById("search-form");
const queryInput = document.getElementById("query-input");
const modeSelect = document.getElementById("mode-select");
const topKSelect = document.getElementById("top-k-select");
const brandInput = document.getElementById("brand-input");
const colorInput = document.getElementById("color-input");
const debugToggle = document.getElementById("debug-toggle");
const resetButton = document.getElementById("reset-button");
const compareButton = document.getElementById("compare-button");
const closeCompareButton = document.getElementById("close-compare");
const compareDrawer = document.getElementById("compare-drawer");
const compareBody = document.getElementById("compare-body");
const compareCaption = document.getElementById("compare-caption");

const loadingState = document.getElementById("loading-state");
const emptyState = document.getElementById("empty-state");
const resultsList = document.getElementById("results-list");
const resultsMeta = document.getElementById("results-meta");
const resultsSubtitle = document.getElementById("results-subtitle");
const summaryStrip = document.getElementById("summary-strip");
const statusBanner = document.getElementById("status-banner");
const historyList = document.getElementById("history-list");

const historyKey = "esci-search-history";
const sessionLatencyKey = "esci-search-latencies";

let queryHistory = JSON.parse(sessionStorage.getItem(historyKey) || "[]");
let sessionLatencies = JSON.parse(sessionStorage.getItem(sessionLatencyKey) || "[]");
let currentPayload = null;

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const formatNumber = (value, digits = 3) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(digits);
};

const formatMs = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toFixed(1)} ms`;
};

const percentile = (values, p) => {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const index = Math.round((ordered.length - 1) * p);
  return ordered[index];
};

const sessionStats = () => {
  if (!sessionLatencies.length) return { p50: null, p95: null };
  return {
    p50: percentile(sessionLatencies, 0.5),
    p95: percentile(sessionLatencies, 0.95),
  };
};

const updateHistory = (entry) => {
  queryHistory = [entry, ...queryHistory.filter((item) => item.key !== entry.key)].slice(0, 8);
  sessionStorage.setItem(historyKey, JSON.stringify(queryHistory));
  renderHistory();
};

const recordLatency = (latencyMs) => {
  sessionLatencies = [...sessionLatencies, latencyMs].slice(-50);
  sessionStorage.setItem(sessionLatencyKey, JSON.stringify(sessionLatencies));
};

const previewText = (result) => {
  const lines = (result.searchable_text || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const useful = lines.slice(3).join(" ").trim() || lines.join(" ").trim();
  if (!useful) return "No searchable text preview available.";
  return useful.length > 240 ? `${useful.slice(0, 240)}…` : useful;
};

const modeLabel = (value) => config.modeLabels[value] || value;

const deriveBadges = (result, query, usedMode) => {
  const badges = [];
  const details = result.debug_details || {};
  const featureSnapshot = details.feature_snapshot || {};
  const queryLower = query.toLowerCase();
  const titleLower = (result.product_title || "").toLowerCase();
  if (featureSnapshot.brand_exact_match || ((result.product_brand || "").toLowerCase() && queryLower.includes((result.product_brand || "").toLowerCase()))) {
    badges.push({ label: "brand match", className: "brand" });
  }
  if (featureSnapshot.title_exact_match) {
    badges.push({ label: "title exact", className: "" });
  } else if ((featureSnapshot.title_token_coverage || 0) >= 0.5 || titleLower.includes(queryLower)) {
    badges.push({ label: "title overlap", className: "" });
  }
  if ((result.raw_scores?.vector || 0) > 0) {
    badges.push({ label: "vector hit", className: "vector" });
  }
  if (usedMode === "ltr") {
    badges.push({ label: "reranked", className: "reranked" });
  }
  return badges;
};

const renderSummary = (payload, e2eMs) => {
  const timing = payload.timings_ms || {};
  const rankingMs = timing.feature_hydration_and_l2 || 0;
  const rerankingMs = timing.reranking || 0;
  const stats = sessionStats();
  summaryStrip.classList.remove("is-empty");
  summaryStrip.innerHTML = [
    { label: "Query", value: payload.query },
    { label: "Mode", value: modeLabel(payload.used_mode) },
    { label: "Results", value: String(payload.results.length) },
    { label: "E2E", value: formatMs(e2eMs) },
    { label: "Retrieval", value: formatMs(timing.retrieval) },
    { label: "Ranking", value: formatMs(rankingMs) },
    { label: "Rerank", value: formatMs(rerankingMs) },
    { label: "Session P50", value: formatMs(stats.p50) },
    { label: "Session P95", value: formatMs(stats.p95) },
    { label: "Request", value: payload.request_id || "—" },
  ]
    .map(
      (item) =>
        `<div class="stat-pill"><span>${escapeHtml(item.label)}:</span><strong>${escapeHtml(item.value)}</strong></div>`
    )
    .join("");
};

const renderStatus = (message, type = "info") => {
  if (!message) {
    statusBanner.hidden = true;
    statusBanner.textContent = "";
    statusBanner.className = "status-banner";
    return;
  }
  statusBanner.hidden = false;
  statusBanner.textContent = message;
  statusBanner.className = `status-banner ${type}`;
};

const scoreGrid = (result) => {
  const ranks = result.debug_details?.rank_positions || {};
  return [
    { label: "BM25", value: formatNumber(result.raw_scores?.bm25, 2) },
    { label: "Vector", value: formatNumber(result.raw_scores?.vector, 3) },
    { label: "Hybrid Rank", value: ranks.hybrid_rank ?? "—" },
    { label: "LTR", value: formatNumber(result.raw_scores?.ltr, 2) },
  ]
    .map((item) => `<div class="score-chip"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></div>`)
    .join("");
};

const kvRows = (entries) =>
  entries
    .map(
      ([label, value]) =>
        `<div class="kv-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(
          value === null || value === undefined || value === "" ? "—" : String(value)
        )}</strong></div>`
    )
    .join("");

const renderResultCard = (payload, result) => {
  const badges = deriveBadges(result, payload.query, payload.used_mode)
    .map((badge) => `<span class="badge ${badge.className}">${escapeHtml(badge.label)}</span>`)
    .join("");
  const details = result.debug_details || {};
  const ranks = details.rank_positions || {};
  const features = details.feature_snapshot || {};
  const metadata = details.raw_metadata || {};
  const openAttr = debugToggle.checked ? " open" : "";

  return `
    <article class="result-card">
      <div class="card-head">
        <div class="rank-badge">#${result.rank}</div>
        <div class="card-head-copy">
          <h3 class="result-title">${escapeHtml(result.product_title)}</h3>
          <div class="meta-row">
            <span class="meta-chip">Brand: ${escapeHtml(result.product_brand || "—")}</span>
            <span class="meta-chip">Color: ${escapeHtml(result.product_color || "—")}</span>
            <span class="meta-chip">Locale: ${escapeHtml(result.product_locale)}</span>
            <span class="meta-chip">Product ID: ${escapeHtml(result.product_id)}</span>
          </div>
        </div>
      </div>
      <p class="result-preview">${escapeHtml(previewText(result))}</p>
      <div class="score-grid">${scoreGrid(result)}</div>
      <div class="badge-row">${badges || '<span class="badge">no special signals</span>'}</div>
      <details class="details"${openAttr}>
        <summary>Show details</summary>
        <div class="detail-grid">
          <section class="detail-card">
            <h4>Ranking explanation</h4>
            <div class="kv-list">
              ${kvRows([
                ["Final rank", result.rank],
                ["BM25 rank", ranks.bm25_rank],
                ["Vector rank", ranks.vector_rank],
                ["Hybrid rank", ranks.hybrid_rank],
                ["LTR rank", ranks.ltr_rank],
              ])}
            </div>
          </section>
          <section class="detail-card">
            <h4>Feature snapshot</h4>
            <div class="kv-list">
              ${kvRows([
                ["Title overlap", formatNumber(features.title_token_coverage, 3)],
                ["Brand match", features.brand_exact_match],
                ["Color match", features.color_mention_match],
                ["Text completeness", formatNumber(features.product_text_completeness, 3)],
                ["BM25 norm", formatNumber(features.bm25_score_norm, 3)],
                ["Vector norm", formatNumber(features.vector_score_norm, 3)],
              ])}
            </div>
          </section>
          <section class="detail-card">
            <h4>Raw metadata</h4>
            <div class="kv-list">
              ${kvRows([
                ["Product ID", metadata.product_id || result.product_id],
                ["Locale", metadata.locale || result.product_locale],
                ["Brand", metadata.brand || result.product_brand],
                ["Color", metadata.color || result.product_color],
                ["Fallback", payload.fallback_triggered ? payload.fallback_reason : "none"],
              ])}
            </div>
          </section>
        </div>
      </details>
    </article>
  `;
};

const renderResults = (payload) => {
  currentPayload = payload;
  emptyState.hidden = payload.results.length > 0;
  resultsList.innerHTML = payload.results.map((result) => renderResultCard(payload, result)).join("");
  resultsMeta.innerHTML = `<span>${payload.results.length} cards</span><span>mode used: ${escapeHtml(
    modeLabel(payload.used_mode)
  )}</span>`;
  resultsSubtitle.textContent = payload.fallback_triggered
    ? `Fallback triggered: ${payload.fallback_reason}`
    : "Cards show metadata, scores, badges, and expandable debug details.";
};

const renderHistory = () => {
  if (!queryHistory.length) {
    historyList.innerHTML = '<span class="subtitle">No searches yet.</span>';
    return;
  }
  historyList.innerHTML = queryHistory
    .map(
      (item) =>
        `<button type="button" class="history-chip" data-history-key="${escapeHtml(item.key)}">${escapeHtml(
          item.query
        )}</button>`
    )
    .join("");
};

const openCompareDrawer = () => compareDrawer.classList.add("is-open");
const closeCompareDrawer = () => compareDrawer.classList.remove("is-open");

const renderCompare = async () => {
  const query = queryInput.value.trim();
  if (!query) {
    renderStatus("Enter a query before comparing modes.", "info");
    return;
  }
  openCompareDrawer();
  compareCaption.textContent = `Comparing top 5 for "${query}"`;
  compareBody.innerHTML = "<div class='loading-state'>Loading compare view…</div>";

  const params = new URLSearchParams({
    q: query,
    locale: "us",
    k: "5",
  });
  if (brandInput.value.trim()) params.set("brand", brandInput.value.trim());
  if (colorInput.value.trim()) params.set("color", colorInput.value.trim());

  const modes = ["bm25", "hybrid", "ltr"];
  const results = await Promise.all(
    modes.map(async (mode) => {
      const modeParams = new URLSearchParams(params);
      modeParams.set("mode", mode);
      const response = await fetch(`/search?${modeParams.toString()}`);
      if (!response.ok) throw new Error(`Compare fetch failed for ${mode}`);
      return { mode, payload: await response.json() };
    })
  );

  compareBody.innerHTML = results
    .map(({ mode, payload }) => {
      const items = payload.results
        .map(
          (item) => `
            <div class="compare-item">
              <h4>#${item.rank} ${escapeHtml(item.product_title)}</h4>
              <p>${escapeHtml(item.product_brand || "—")} · ${escapeHtml(item.product_color || "—")} · ${escapeHtml(
            item.product_id
          )}</p>
            </div>
          `
        )
        .join("");
      return `
        <section class="compare-column">
          <div class="compare-column-header">
            <strong>${escapeHtml(modeLabel(mode))}</strong>
            <span class="pill pill-muted">${payload.results.length} results</span>
          </div>
          ${items}
        </section>
      `;
    })
    .join("");
};

const setLoading = (isLoading) => {
  loadingState.hidden = !isLoading;
};

const search = async ({ fromHistory = false, autoCompare = false } = {}) => {
  const query = queryInput.value.trim();
  if (!query) {
    renderStatus("Enter a query to search.", "info");
    return;
  }

  setLoading(true);
  renderStatus("", "info");
  const params = new URLSearchParams({
    q: query,
    mode: modeSelect.value,
    locale: "us",
    k: topKSelect.value,
  });
  if (brandInput.value.trim()) params.set("brand", brandInput.value.trim());
  if (colorInput.value.trim()) params.set("color", colorInput.value.trim());

  const started = performance.now();
  try {
    const response = await fetch(`/search?${params.toString()}`);
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }
    const payload = await response.json();
    const e2eMs = performance.now() - started;
    recordLatency(e2eMs);
    renderSummary(payload, e2eMs);
    renderResults(payload);
    if (!fromHistory) {
      updateHistory({
        key: `${query}::${modeSelect.value}::${topKSelect.value}`,
        query,
        mode: modeSelect.value,
        brand: brandInput.value.trim(),
        color: colorInput.value.trim(),
        k: topKSelect.value,
      });
    }
    renderStatus(
      payload.fallback_triggered
        ? `Fallback used: ${payload.fallback_reason}`
        : `Rendered ${payload.results.length} results in ${formatMs(e2eMs)}.`,
      payload.fallback_triggered ? "error" : "info"
    );
    if (autoCompare) {
      await renderCompare();
    }
  } catch (error) {
    resultsList.innerHTML = "";
    emptyState.hidden = false;
    summaryStrip.classList.add("is-empty");
    summaryStrip.innerHTML = '<div class="summary-empty">Search did not complete.</div>';
    renderStatus(`Backend unavailable: ${error.message}`, "error");
  } finally {
    setLoading(false);
  }
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await search();
});

debugToggle.addEventListener("change", () => {
  document.querySelectorAll(".details").forEach((detail) => {
    detail.open = debugToggle.checked;
  });
});

resetButton.addEventListener("click", () => {
  queryInput.value = "";
  brandInput.value = "";
  colorInput.value = "";
  modeSelect.value = "hybrid";
  topKSelect.value = "10";
  debugToggle.checked = false;
  closeCompareDrawer();
  resultsList.innerHTML = "";
  emptyState.hidden = false;
  resultsMeta.innerHTML = "";
  resultsSubtitle.textContent = "Thin UI for qualitative ranking inspection.";
  summaryStrip.classList.add("is-empty");
  summaryStrip.innerHTML = '<div class="summary-empty">Run a search to see latency, request, and session stats.</div>';
  renderStatus("", "info");
});

compareButton.addEventListener("click", async () => {
  try {
    await renderCompare();
  } catch (error) {
    renderStatus(`Compare view failed: ${error.message}`, "error");
  }
});

closeCompareButton.addEventListener("click", closeCompareDrawer);

historyList.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-history-key]");
  if (!target) return;
  const entry = queryHistory.find((item) => item.key === target.dataset.historyKey);
  if (!entry) return;
  queryInput.value = entry.query;
  modeSelect.value = entry.mode;
  topKSelect.value = entry.k;
  brandInput.value = entry.brand || "";
  colorInput.value = entry.color || "";
  await search({ fromHistory: true });
});

const applyInitialState = async () => {
  queryInput.value = initialState.query || "";
  modeSelect.value = initialState.mode || "hybrid";
  topKSelect.value = String(initialState.k || 10);
  brandInput.value = initialState.brand || "";
  colorInput.value = initialState.color || "";
  debugToggle.checked = Boolean(initialState.debug);
  renderHistory();
  if (initialState.query) {
    await search({ autoCompare: Boolean(initialState.compare) });
  }
};

applyInitialState();

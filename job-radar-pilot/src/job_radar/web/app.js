"use strict";

const elements = {
  searchButton: document.querySelector("#search-button"),
  liveStatus: document.querySelector("#live-status"),
  textFilter: document.querySelector("#text-filter"),
  sourceFilter: document.querySelector("#source-filter"),
  matchFilter: document.querySelector("#match-filter"),
  sortOrder: document.querySelector("#sort-order"),
  trackingFilter: document.querySelector("#tracking-filter"),
  downloadCsv: document.querySelector("#download-csv"),
  tableBody: document.querySelector("#jobs-table-body"),
  emptyState: document.querySelector("#empty-state"),
  visibleCount: document.querySelector("#visible-count"),
  sourceStatuses: document.querySelector("#source-statuses"),
  toggleSources: document.querySelector("#toggle-sources"),
  summaryJobs: document.querySelector("#summary-jobs"),
  summarySources: document.querySelector("#summary-sources"),
  summaryMatches: document.querySelector("#summary-matches"),
  summaryDate: document.querySelector("#summary-date"),
  summaryTime: document.querySelector("#summary-time"),
  footerVersion: document.querySelector("#footer-version"),
  preferencesButton: document.querySelector("#preferences-button"),
  preferencesPanel: document.querySelector("#preferences-panel"),
  closePreferences: document.querySelector("#close-preferences"),
  preferencesForm: document.querySelector("#preferences-form"),
  preferencesStatus: document.querySelector("#preferences-status"),
  searchTerms: document.querySelector("#search-terms"),
  locationScopes: document.querySelector("#location-scopes"),
  technologies: document.querySelector("#technologies"),
  excludedTerms: document.querySelector("#excluded-terms"),
  seniorityInternship: document.querySelector("#seniority-internship"),
  seniorityJunior: document.querySelector("#seniority-junior"),
  workplaceRemote: document.querySelector("#workplace-remote"),
  workplaceHybrid: document.querySelector("#workplace-hybrid"),
  workplaceOnsite: document.querySelector("#workplace-onsite"),
  downloadReport: document.querySelector("#download-report"),
  linkedinButton: document.querySelector("#linkedin-button"),
  linkedinPanel: document.querySelector("#linkedin-panel"),
  closeLinkedin: document.querySelector("#close-linkedin"),
  linkedinSearches: document.querySelector("#linkedin-searches"),
  linkedinFilters: document.querySelector("#linkedin-filters"),
};

let dashboardState = { jobs: [], report: {}, status: "IDLE", sources: {} };
let refreshTimer;
let preferencesLoaded = false;
let trackingState = {};
const TRACKING_OPTIONS = [
  ["", "—"],
  ["SAVED", "Salva"],
  ["APPLIED", "Aplicada"],
  ["DISCARDED", "Descartada"],
];
const TRACKED_FILTER_STATUS = { saved: "SAVED", applied: "APPLIED", discarded: "DISCARDED" };
let linkedinLoaded = false;

function normalized(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function fitState(job) {
  const label = (job.match_labels ?? []).find((item) =>
    /^FIT:(READY|CONDITIONAL|EXCLUDE|AMBIGUOUS)$/.test(String(item))
  );
  return label ? String(label).slice(4) : "AMBIGUOUS";
}

function fitScore(job) {
  const label = (job.match_labels ?? []).find((item) =>
    /^FIT_SCORE:-?\d+$/.test(String(item))
  );
  return label ? Number(String(label).slice("FIT_SCORE:".length)) : Number.NEGATIVE_INFINITY;
}

function fitLabel(state) {
  return {
    READY: "Mais compatível",
    CONDITIONAL: "A revisar",
    EXCLUDE: "Fora do perfil",
    AMBIGUOUS: "Dados insuficientes",
  }[state] || "Dados insuficientes";
}

function searchValues(value) {
  if (Array.isArray(value)) return value.flatMap(searchValues);
  if (value && typeof value === "object") return Object.values(value).flatMap(searchValues);
  return [value];
}

function filteredJobs() {
  const text = normalized(elements.textFilter.value.trim());
  const source = elements.sourceFilter.value;
  const match = elements.matchFilter.value;
  const tracked = elements.trackingFilter.value;

  return (dashboardState.jobs ?? []).filter((job) => {
    const trackedStatus = trackingStatus(job);
    if (tracked === "active" && trackedStatus === "DISCARDED") return false;
    if (TRACKED_FILTER_STATUS[tracked] && trackedStatus !== TRACKED_FILTER_STATUS[tracked]) return false;
    const haystack = normalized([
      job.title,
      job.company,
      job.location,
      ...(job.technologies ?? []),
      ...(job.match_labels ?? []),
      ...searchValues(job.description_summary),
      ...searchValues(job.requirements),
      ...searchValues(job.evidence_snippets),
      job.seniority,
      job.remote_scope,
    ].join(" "));
    if (text && !haystack.includes(text)) return false;
    if (source && job.source !== source) return false;
    const state = fitState(job);
    if (match === "ready" && state !== "READY") return false;
    if (match === "review" && !["CONDITIONAL", "AMBIGUOUS"].includes(state)) return false;
    if (match === "exclude" && state !== "EXCLUDE") return false;
    return true;
  }).sort((left, right) => {
    const order = { READY: 0, CONDITIONAL: 1, AMBIGUOUS: 2, EXCLUDE: 3 };
    const byState = order[fitState(left)] - order[fitState(right)];
    const byFit = byState || fitScore(right) - fitScore(left);
    if (elements.sortOrder.value !== "recent") return byFit;
    return publishedTime(right) - publishedTime(left) || byFit;
  });
}

function trackingStatus(job) {
  return trackingState[job.canonical_url]?.status ?? "";
}

async function loadTracking() {
  try {
    const response = await fetch("/api/tracking", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    trackingState = payload.jobs ?? {};
  } catch (error) {
    elements.liveStatus.textContent = `Acompanhamento indisponível: ${error.message}`;
  }
  renderTable();
}

async function updateTracking(job, status, select) {
  select.disabled = true;
  try {
    const response = await fetch("/api/tracking", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: job.canonical_url, status: status || null }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    trackingState = payload.jobs ?? {};
  } catch (error) {
    elements.liveStatus.textContent = `Não foi possível salvar o acompanhamento: ${error.message}`;
  } finally {
    select.disabled = false;
    renderTable();
  }
}

function trackingCell(job) {
  const cell = document.createElement("td");
  const select = document.createElement("select");
  select.className = "tracking-select";
  select.setAttribute("aria-label", `Acompanhamento da vaga ${job.title || ""}`);
  TRACKING_OPTIONS.forEach(([value, label]) => select.appendChild(new Option(label, value)));
  select.value = trackingStatus(job);
  select.disabled = !/^https?:\/\//.test(job.canonical_url ?? "");
  select.addEventListener("change", () => updateTracking(job, select.value, select));
  cell.appendChild(select);
  return cell;
}

function publishedTime(job) {
  const time = Date.parse(job.published_at ?? "");
  return Number.isNaN(time) ? -Infinity : time;
}

function publishedLabel(job) {
  const time = publishedTime(job);
  if (time === -Infinity) return "";
  return new Date(time).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function renderTable() {
  const jobs = filteredJobs();
  elements.tableBody.replaceChildren();

  jobs.forEach((job) => {
    const row = document.createElement("tr");
    const trackedStatus = trackingStatus(job);
    if (trackedStatus) row.className = `tracked-${trackedStatus.toLowerCase()}`;
    const titleCell = document.createElement("td");
    titleCell.append(
      textElement("div", "job-title", job.title || "Cargo não informado"),
      textElement(
        "span",
        "job-meta",
        [
          (job.technologies ?? []).slice(0, 4).join(" · ") || "Tecnologias não informadas",
          publishedLabel(job) && `publicada em ${publishedLabel(job)}`,
        ].filter(Boolean).join(" — ")
      )
    );
    row.appendChild(titleCell);
    row.appendChild(textElement("td", "", job.company || "Não informada"));
    row.appendChild(textElement("td", "", job.location || job.remote_scope || "Não informado"));

    const sourceCell = document.createElement("td");
    sourceCell.appendChild(textElement("span", "source-pill", job.source || "—"));
    row.appendChild(sourceCell);

    const matchCell = document.createElement("td");
    matchCell.appendChild(
      textElement(
        "span",
        `match-pill ${fitState(job).toLowerCase()}`,
        fitLabel(fitState(job))
      )
    );
    if ((job.match_labels ?? []).includes("STATUS:NEW")) {
      matchCell.appendChild(textElement("span", "match-pill new", "Nova"));
    }
    row.appendChild(matchCell);
    row.appendChild(trackingCell(job));

    const actionCell = document.createElement("td");
    const link = document.createElement("a");
    link.className = "open-link";
    link.href = job.canonical_url || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", `Abrir vaga ${job.title || ""}`);
    link.textContent = "↗";
    actionCell.appendChild(link);
    row.appendChild(actionCell);
    elements.tableBody.appendChild(row);
  });

  elements.visibleCount.textContent = `${jobs.length} ${jobs.length === 1 ? "vaga" : "vagas"}`;
  elements.emptyState.hidden = jobs.length !== 0;
  const reportParameters = new URLSearchParams();
  if (elements.textFilter.value.trim()) reportParameters.set("text", elements.textFilter.value.trim());
  if (elements.sourceFilter.value) reportParameters.set("source", elements.sourceFilter.value);
  if (elements.matchFilter.value) reportParameters.set("match", elements.matchFilter.value);
  if (elements.trackingFilter.value) reportParameters.set("tracked", elements.trackingFilter.value);
  const reportQuery = reportParameters.toString();
  elements.downloadReport.href = `/api/export/markdown${reportQuery ? `?${reportQuery}` : ""}`;
  elements.downloadCsv.href = `/api/export/csv${reportQuery ? `?${reportQuery}` : ""}`;
}

function updateSourceFilter() {
  const selected = elements.sourceFilter.value;
  const sources = new Set((dashboardState.jobs ?? []).map((job) => job.source).filter(Boolean));
  (dashboardState.report?.sources ?? []).forEach((source) => sources.add(source.source));
  const options = [new Option("Todos os portais", "")];
  [...sources].sort().forEach((source) => options.push(new Option(source, source)));
  elements.sourceFilter.replaceChildren(...options);
  elements.sourceFilter.value = sources.has(selected) ? selected : "";
}

function renderSummary() {
  const jobs = dashboardState.jobs ?? [];
  const productiveSources = new Set(jobs.map((job) => job.source).filter(Boolean));
  elements.summaryJobs.textContent = String(jobs.length);
  elements.summarySources.textContent = String(productiveSources.size);
  elements.summaryMatches.textContent = String(jobs.filter((job) => fitState(job) === "READY").length);

  const finishedAt = dashboardState.report?.finished_at || dashboardState.finished_at;
  if (finishedAt) {
    const date = new Date(finishedAt);
    elements.summaryDate.textContent = new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit",
      month: "short",
    }).format(date);
    elements.summaryTime.textContent = new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } else {
    elements.summaryDate.textContent = "—";
    elements.summaryTime.textContent = "aguardando dados";
  }
  const version = dashboardState.report?.scrapling_version;
  elements.footerVersion.textContent = version ? `Scrapling ${version}` : "Scrapling";
}

function statusClass(status) {
  const value = normalized(status);
  if (value === "success" || value === "done") return "success";
  if (value === "partial" || value === "empty") return value;
  if (value === "blocked" || value === "auth_required") return "blocked";
  return "error";
}

function statusLabel(status) {
  return {
    SUCCESS: "OK",
    DONE: "OK",
    PARTIAL: "Parcial",
    EMPTY: "Sem vagas",
    ERROR: "Erro",
    BLOCKED: "Bloqueado",
    AUTH_REQUIRED: "Login",
  }[status] || status || "Pendente";
}

function countWarningText(warning) {
  const match = /^SOURCE_COUNT_(DROP|ZERO):(\d+)<(\d+)$/.exec(String(warning));
  if (!match) return "";
  const [, kind, current, average] = match;
  return kind === "ZERO"
    ? `Coleta zerou (média anterior: ${average}); o portal pode ter mudado.`
    : `Queda para ${current} vagas (média anterior: ${average}); confira o portal.`;
}

function renderSources() {
  const liveSources = Object.values(dashboardState.sources ?? {});
  const reportSources = dashboardState.report?.sources ?? [];
  const sources = liveSources.length ? liveSources : reportSources;
  elements.sourceStatuses.replaceChildren();
  sources.forEach((source) => {
    const row = document.createElement("article");
    row.className = "source-row";
    const copy = document.createElement("div");
    copy.append(
      textElement("strong", "", source.source || "Portal"),
      textElement(
        "small",
        "",
        `${source.records ?? 0} registros · ${source.stop_reason || "concluído"}`
      )
    );
    const reported = reportSources.find((item) => item.source === source.source);
    (source.warnings ?? reported?.warnings ?? [])
      .map(countWarningText)
      .filter(Boolean)
      .forEach((text) => copy.appendChild(textElement("small", "source-warning", text)));
    row.append(
      copy,
      textElement(
        "span",
        `status-pill ${statusClass(source.status)}`,
        statusLabel(source.status)
      )
    );
    elements.sourceStatuses.appendChild(row);
  });
}

function renderRunState() {
  const running = dashboardState.status === "RUNNING";
  elements.searchButton.disabled = running;
  elements.searchButton.classList.toggle("running", running);
  const messages = {
    IDLE: "Resultados locais carregados.",
    RUNNING: "Buscando vagas… acompanhe os portais abaixo.",
    DONE: "Busca concluída com sucesso.",
    PARTIAL: "Busca concluída; alguns portais exigem atenção.",
    ERROR: dashboardState.error || "A busca encontrou um erro.",
  };
  elements.liveStatus.textContent = dashboardState.read_error
    ? `Não foi possível ler a saída: ${dashboardState.read_error}`
    : messages[dashboardState.status] || "Painel pronto.";
}

function render() {
  updateSourceFilter();
  renderSummary();
  renderTable();
  renderSources();
  renderRunState();
}

async function refreshState() {
  window.clearTimeout(refreshTimer);
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    dashboardState = await response.json();
    render();
  } catch (error) {
    elements.liveStatus.textContent = `Interface sem conexão com o coletor: ${error.message}`;
  }
  const delay = dashboardState.status === "RUNNING" ? 900 : 5000;
  refreshTimer = window.setTimeout(refreshState, delay);
}

async function startSearch() {
  elements.searchButton.disabled = true;
  elements.liveStatus.textContent = "Iniciando busca…";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    await refreshState();
  } catch (error) {
    elements.liveStatus.textContent = `Não foi possível iniciar: ${error.message}`;
    elements.searchButton.disabled = false;
  }
}

function setChecked(element, values) {
  element.checked = values.includes(element.value);
}

function showPreferences(show) {
  elements.preferencesPanel.hidden = !show;
  elements.preferencesButton.setAttribute("aria-expanded", String(show));
}

function showLinkedin(show) {
  elements.linkedinPanel.hidden = !show;
  elements.linkedinButton.setAttribute("aria-expanded", String(show));
}

async function loadLinkedinSearches() {
  if (linkedinLoaded) return;
  elements.linkedinButton.disabled = true;
  elements.linkedinSearches.replaceChildren(
    textElement("p", "linkedin-loading", "Preparando pesquisas…")
  );
  try {
    const response = await fetch("/api/linkedin-searches", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const terms = (payload.searches ?? []).map((search) => {
      const row = document.createElement("div");
      row.className = "linkedin-term";
      row.appendChild(textElement("span", "", search.label));
      const copy = document.createElement("button");
      copy.type = "button";
      copy.textContent = "Copiar";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(search.label);
          copy.textContent = "Copiado";
        } catch (error) {
          elements.linkedinFilters.textContent = `Copie manualmente: ${search.label}`;
        }
      });
      row.appendChild(copy);
      return row;
    });
    elements.linkedinSearches.replaceChildren(...terms);
    const filters = payload.filters ?? {};
    const levels = (filters.seniority_levels ?? []).join(", ") || "qualquer nível";
    const models = (filters.workplace_models ?? []).join(", ") || "qualquer modelo";
    const locations = (filters.location_scopes ?? []).join(", ");
    elements.linkedinFilters.textContent = `Filtros para conferir no LinkedIn: ${levels} · ${models} · ${locations}`;
    linkedinLoaded = true;
  } catch (error) {
    elements.linkedinSearches.replaceChildren(
      textElement("p", "linkedin-loading", `Não foi possível preparar: ${error.message}`)
    );
  } finally {
    elements.linkedinButton.disabled = false;
  }
}

async function loadPreferences() {
  if (preferencesLoaded) return true;
  const controls = [...elements.preferencesForm.querySelectorAll("input, textarea, button")];
  controls.forEach((control) => { control.disabled = true; });
  elements.preferencesStatus.textContent = "Carregando configurações…";
  try {
    const response = await fetch("/api/preferences", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    elements.searchTerms.value = (payload.search_terms ?? []).join("\n");
    elements.locationScopes.value = (payload.location_scopes ?? []).join("\n");
    elements.technologies.value = (payload.technologies ?? []).join("\n");
    elements.excludedTerms.value = (payload.excluded_terms ?? []).join("\n");
    setChecked(elements.seniorityInternship, payload.seniority_levels ?? []);
    setChecked(elements.seniorityJunior, payload.seniority_levels ?? []);
    setChecked(elements.workplaceRemote, payload.workplace_models ?? []);
    setChecked(elements.workplaceHybrid, payload.workplace_models ?? []);
    setChecked(elements.workplaceOnsite, payload.workplace_models ?? []);
    preferencesLoaded = true;
    elements.preferencesStatus.textContent = "Configurações atuais carregadas.";
    return true;
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível carregar: ${error.message}`;
    return false;
  } finally {
    controls.forEach((control) => { control.disabled = false; });
  }
}

function linesFrom(element) {
  return element.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function checkedValues(elementsList) {
  return elementsList.filter((element) => element.checked).map((element) => element.value);
}

async function savePreferences(event) {
  event.preventDefault();
  const saveButton = document.querySelector("#save-preferences");
  saveButton.disabled = true;
  elements.preferencesStatus.textContent = "Salvando configurações…";
  const payload = {
    search_terms: linesFrom(elements.searchTerms),
    seniority_levels: checkedValues([
      elements.seniorityInternship,
      elements.seniorityJunior,
    ]),
    workplace_models: checkedValues([
      elements.workplaceRemote,
      elements.workplaceHybrid,
      elements.workplaceOnsite,
    ]),
    location_scopes: linesFrom(elements.locationScopes),
    technologies: linesFrom(elements.technologies),
    excluded_terms: linesFrom(elements.excludedTerms),
  };
  if (payload.seniority_levels.length === 0) {
    elements.preferencesStatus.textContent = "Selecione Estágio e/ou Júnior.";
    saveButton.disabled = false;
    return;
  }
  if (payload.location_scopes.length === 0) {
    elements.preferencesStatus.textContent = "Informe ao menos uma localidade.";
    saveButton.disabled = false;
    return;
  }
  try {
    const response = await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.error || `HTTP ${response.status}`);
    preferencesLoaded = true;
    linkedinLoaded = false;
    elements.preferencesStatus.textContent = "Configurações salvas. Clique em Buscar vagas agora quando quiser.";
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível salvar: ${error.message}`;
  } finally {
    saveButton.disabled = false;
  }
}

elements.searchButton.addEventListener("click", startSearch);
elements.preferencesButton.addEventListener("click", async () => {
  const willShow = elements.preferencesPanel.hidden;
  showPreferences(willShow);
  if (willShow) await loadPreferences();
});
elements.closePreferences.addEventListener("click", () => showPreferences(false));
elements.preferencesForm.addEventListener("submit", savePreferences);
elements.linkedinButton.addEventListener("click", async () => {
  const willShow = elements.linkedinPanel.hidden;
  showLinkedin(willShow);
  if (willShow) await loadLinkedinSearches();
});
elements.closeLinkedin.addEventListener("click", () => showLinkedin(false));
[
  elements.textFilter,
  elements.sourceFilter,
  elements.matchFilter,
  elements.sortOrder,
  elements.trackingFilter,
].forEach((filter) => {
  filter.addEventListener("input", renderTable);
  filter.addEventListener("change", renderTable);
});
elements.toggleSources.addEventListener("click", () => {
  const willShow = elements.sourceStatuses.hidden;
  elements.sourceStatuses.hidden = !willShow;
  elements.toggleSources.textContent = willShow ? "Ocultar detalhes" : "Ver detalhes";
});

refreshState();
loadTracking();

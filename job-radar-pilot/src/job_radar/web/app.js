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
  clearFilters: document.querySelector("#clear-filters"),
  cleanupButton: document.querySelector("#cleanup-button"),
  cleanupPanel: document.querySelector("#cleanup-panel"),
  closeCleanup: document.querySelector("#close-cleanup"),
  cleanupOverview: document.querySelector("#cleanup-overview"),
  cleanupDiscarded: document.querySelector("#cleanup-discarded"),
  cleanupSamples: document.querySelector("#cleanup-samples"),
  cleanupUndo: document.querySelector("#cleanup-undo"),
  undoBox: document.querySelector("#undo-box"),
  undoInfo: document.querySelector("#undo-info"),
  cardAll: document.querySelector("#card-all"),
  cardReady: document.querySelector("#card-ready"),
  exportAi: document.querySelector("#export-ai"),
  exportButton: document.querySelector("#export-button"),
  exportPanel: document.querySelector("#export-panel"),
  closeExport: document.querySelector("#close-export"),
  exportMatch: document.querySelector("#export-match"),
  exportMinScore: document.querySelector("#export-min-score"),
  exportAge: document.querySelector("#export-age"),
  exportTracked: document.querySelector("#export-tracked"),
  exportSource: document.querySelector("#export-source"),
  exportCount: document.querySelector("#export-count"),
  exportXlsx: document.querySelector("#export-xlsx"),
  exportCsv: document.querySelector("#export-csv"),
  exportMd: document.querySelector("#export-md"),
  linkedinButton: document.querySelector("#linkedin-button"),
  linkedinPanel: document.querySelector("#linkedin-panel"),
  closeLinkedin: document.querySelector("#close-linkedin"),
  linkedinSearches: document.querySelector("#linkedin-searches"),
  linkedinFilters: document.querySelector("#linkedin-filters"),
  linkedinPeriod: document.querySelector("#linkedin-period"),
  linkedinImportText: document.querySelector("#linkedin-import-text"),
  linkedinImportButton: document.querySelector("#linkedin-import-button"),
  linkedinImportStatus: document.querySelector("#linkedin-import-status"),
  quickSearchButton: document.querySelector("#quick-search-button"),
  sourcesButton: document.querySelector("#sources-button"),
  sourcesPicker: document.querySelector("#sources-picker"),
  sourcesList: document.querySelector("#sources-list"),
  sourcesStatus: document.querySelector("#sources-status"),
  closeSources: document.querySelector("#close-sources"),
  selectTech: document.querySelector("#select-tech"),
  selectAll: document.querySelector("#select-all"),
  searchSelected: document.querySelector("#search-selected"),
  summaryReview: document.querySelector("#summary-review"),
  moreRow: document.querySelector("#more-row"),
  showMore: document.querySelector("#show-more"),
  seniorityMid: document.querySelector("#seniority-mid"),
  senioritySenior: document.querySelector("#seniority-senior"),
  profileSelect: document.querySelector("#profile-select"),
  profileName: document.querySelector("#profile-name"),
  profileSave: document.querySelector("#profile-save"),
  profileDelete: document.querySelector("#profile-delete"),
  stackChips: document.querySelector("#stack-chips"),
  applySuggestions: document.querySelector("#apply-suggestions"),
  ruleOffTopic: document.querySelector("#rule-off-topic"),
  ruleExcluded: document.querySelector("#rule-excluded"),
  ruleExpired: document.querySelector("#rule-expired"),
  ruleAge: document.querySelector("#rule-age"),
  rulesStatus: document.querySelector("#rules-status"),
  cleanupBreakdown: document.querySelector("#cleanup-breakdown"),
  cleanupPreview: document.querySelector("#cleanup-preview"),
  cleanupRun: document.querySelector("#cleanup-run"),
  cleanupStatus: document.querySelector("#cleanup-status"),
};

const FILTER_KEY = "radar.filters";
const FILTER_DEFAULTS = { match: "", sort: "fit", tracked: "active" };
const expandedJobs = new Set();

function saveFilters() {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify({
      match: elements.matchFilter.value,
      sort: elements.sortOrder.value,
      tracked: elements.trackingFilter.value,
    }));
  } catch (error) { /* armazenamento indisponível: segue sem lembrar */ }
}

function restoreFilters() {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTER_KEY) || "{}");
    const apply = (select, value) => {
      if (typeof value === "string" && [...select.options].some((o) => o.value === value)) {
        select.value = value;
      }
    };
    apply(elements.matchFilter, saved.match);
    apply(elements.sortOrder, saved.sort);
    apply(elements.trackingFilter, saved.tracked);
  } catch (error) { /* valor salvo inválido: ignora */ }
}

function filtersAreDefault() {
  return !elements.textFilter.value.trim()
    && !elements.sourceFilter.value
    && elements.matchFilter.value === FILTER_DEFAULTS.match
    && elements.sortOrder.value === FILTER_DEFAULTS.sort
    && elements.trackingFilter.value === FILTER_DEFAULTS.tracked;
}

function resetFilters() {
  elements.textFilter.value = "";
  elements.sourceFilter.value = "";
  elements.matchFilter.value = FILTER_DEFAULTS.match;
  elements.sortOrder.value = FILTER_DEFAULTS.sort;
  elements.trackingFilter.value = FILTER_DEFAULTS.tracked;
  saveFilters();
  visibleRows = ROW_PAGE_SIZE;
  renderTable();
}

function focusResults(match) {
  elements.textFilter.value = "";
  elements.sourceFilter.value = "";
  elements.matchFilter.value = match;
  elements.trackingFilter.value = "active";
  saveFilters();
  visibleRows = ROW_PAGE_SIZE;
  renderTable();
  document.querySelector(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
}

const CRITERIA_LABELS = [
  ["TECH_MATCH:", "Tecnologia"],
  ["SENIORITY_MATCH:", "Nível"],
  ["LOCATION_MATCH:", "Local"],
  ["WORKPLACE_MATCH:", "Modelo"],
];

function jobScore(job) {
  const state = fitState(job);
  const points = fitScore(job);
  if (state === "EXCLUDE" || points < 0 || !Number.isFinite(points)) return 0;
  let score = points * 20 + (state === "READY" ? 10 : 0);
  const published = publishedTime(job);
  if (published !== -Infinity) {
    const days = (Date.now() - published) / 86400000;
    const bonus = days <= 3 ? 10 : days <= 7 ? 7 : days <= 14 ? 4 : days <= 30 ? 2 : 0;
    score += bonus;
  }
  return Math.min(100, score);
}

function detailRow(job) {
  const row = document.createElement("tr");
  row.className = "detail-row";
  const cell = document.createElement("td");
  cell.colSpan = 7;
  const box = document.createElement("div");
  box.className = "job-detail";
  const summary = String(job.description_summary ?? "").trim();
  box.appendChild(textElement("p", "detail-text", summary ? summary.slice(0, 700) + (summary.length > 700 ? "…" : "") : "Sem descrição disponível nesta fonte — abra a vaga para ler completa."));
  const labels = (job.match_labels ?? []).map(String);
  const criteria = CRITERIA_LABELS.flatMap(([prefix, name]) =>
    labels.filter((l) => l.startsWith(prefix)).map((l) => `${name}: ${l.slice(prefix.length)}`)
  );
  const facts = [
    `Score ${jobScore(job)}/100`,
    criteria.length ? `Critérios atendidos — ${criteria.join(" · ")}` : "Nenhum critério do perfil confirmado",
  ];
  const reasons = fitReasons(job);
  if (reasons.length) facts.push(`Atenção — ${reasons.join(" · ")}`);
  const also = alsoSeenIn(job);
  if (also.length) facts.push(`Também em ${also.join(", ")}`);
  if (job.employment_type) facts.push(`Contrato: ${job.employment_type}`);
  if (publishedLabel(job)) facts.push(`Publicada em ${publishedLabel(job)}`);
  const list = document.createElement("ul");
  list.className = "detail-facts";
  facts.forEach((fact) => list.appendChild(textElement("li", "", fact)));
  box.appendChild(list);
  const techs = document.createElement("div");
  techs.className = "detail-techs";
  (job.technologies ?? []).forEach((tech) => techs.appendChild(textElement("span", "tech-chip", tech)));
  if (techs.childElementCount) box.appendChild(techs);
  cell.appendChild(box);
  row.appendChild(cell);
  return row;
}

const ROW_PAGE_SIZE = 300;
let visibleRows = ROW_PAGE_SIZE;
let configuredSources = [];
const REASON_LABELS = [
  ["RELEVANCE:OFF_TOPIC", "fora da área de tecnologia"],
  ["SENIORITY_MISMATCH:", "nível acima do desejado"],
  ["LOCATION_MISMATCH:", "fora das localidades escolhidas"],
  ["WORKPLACE_MISMATCH:", "modelo de trabalho diferente"],
  ["LOCATION_UNCLEAR:", "local não confirmado"],
  ["WORKPLACE_UNCLEAR:", "modelo de trabalho não confirmado"],
  ["SENIORITY_UNCLEAR:", "faixa de nível ampla (júnior/pleno)"],
  ["ELIGIBILITY_UNCLEAR:", "vaga com público restrito"],
];

function isOffTopic(job) {
  return (job.match_labels ?? []).includes("RELEVANCE:OFF_TOPIC");
}

function fitReasons(job) {
  const labels = (job.match_labels ?? []).map(String);
  const reasons = REASON_LABELS
    .filter(([prefix]) => labels.some((label) => label.startsWith(prefix)))
    .map(([, text]) => text);
  if (!reasons.length && fitState(job) === "AMBIGUOUS") reasons.push("poucos dados para avaliar");
  return reasons;
}

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
    if (tracked === "new" && (trackedStatus || !(job.match_labels ?? []).includes("STATUS:NEW"))) return false;
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
    const offTopic = isOffTopic(job);
    if (match === "offtopic") {
      if (!offTopic) return false;
    } else if (match !== "all" && offTopic) {
      return false;
    }
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

function alsoSeenIn(job) {
  return (job.match_labels ?? [])
    .filter((label) => String(label).startsWith("ALSO_SEEN_IN:"))
    .map((label) => String(label).slice("ALSO_SEEN_IN:".length));
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

const WORKPLACE_LABELS = { REMOTE: "Remoto", HYBRID: "Híbrido", ONSITE: "Presencial" };

function renderTable() {
  const jobs = filteredJobs();
  elements.tableBody.replaceChildren();

  jobs.slice(0, visibleRows).forEach((job) => {
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
          alsoSeenIn(job).length && `também em ${alsoSeenIn(job).join(", ")}`,
        ].filter(Boolean).join(" — ")
      )
    );
    const expanded = expandedJobs.has(job.canonical_url);
    titleCell.classList.add("title-cell");
    titleCell.setAttribute("role", "button");
    titleCell.tabIndex = 0;
    titleCell.setAttribute("aria-expanded", String(expanded));
    titleCell.title = expanded ? "Ocultar detalhes" : "Ver detalhes da vaga";
    const toggle = () => {
      if (expandedJobs.has(job.canonical_url)) expandedJobs.delete(job.canonical_url);
      else expandedJobs.add(job.canonical_url);
      renderTable();
    };
    titleCell.addEventListener("click", toggle);
    titleCell.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
    });
    if (expanded) row.classList.add("expanded");
    row.appendChild(titleCell);
    row.appendChild(textElement("td", "", job.company || "Não informada"));
    const locationCell = textElement("td", "", job.location || job.remote_scope || "Não informado");
    const workplace = WORKPLACE_LABELS[job.workplace_model];
    if (workplace) locationCell.appendChild(textElement("small", `workplace-tag ${job.workplace_model.toLowerCase()}`, workplace));
    row.appendChild(locationCell);

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
    const reasons = fitReasons(job);
    if (fitState(job) !== "READY" && reasons.length) {
      matchCell.appendChild(textElement("small", "reason", reasons.slice(0, 2).join(" · ")));
      matchCell.title = reasons.join(" · ");
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
    if (expanded) elements.tableBody.appendChild(detailRow(job));
  });
  elements.clearFilters.hidden = filtersAreDefault();

  const shown = Math.min(jobs.length, visibleRows);
  elements.visibleCount.textContent =
    jobs.length > shown
      ? `${shown} de ${jobs.length} vagas`
      : `${jobs.length} ${jobs.length === 1 ? "vaga" : "vagas"}`;
  elements.moreRow.hidden = jobs.length <= shown;
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
  const toReview = jobs.filter((job) => fitState(job) === "CONDITIONAL" && !isOffTopic(job)).length;
  elements.summaryReview.textContent = `mais compatíveis · ${toReview} a revisar`;

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
  elements.quickSearchButton.disabled = running;
  elements.searchSelected.disabled = running;
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

async function loadConfiguredSources() {
  if (configuredSources.length) return true;
  try {
    const response = await fetch("/api/sources", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    configuredSources = payload.sources ?? [];
    return configuredSources.length > 0;
  } catch (error) {
    elements.sourcesStatus.textContent = `Não foi possível listar os portais: ${error.message}`;
    return false;
  }
}

function renderSourcesPicker() {
  elements.sourcesList.replaceChildren(
    ...configuredSources.map((source) => {
      const label = document.createElement("label");
      label.className = "check-option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = source.code;
      input.checked = true;
      label.append(input, ` ${source.code} `);
      if (source.tech_focus) label.appendChild(textElement("span", "tech-tag", "TI"));
      return label;
    })
  );
}

function pickedSources() {
  return [...elements.sourcesList.querySelectorAll("input:checked")].map((input) => input.value);
}

function setPicked(predicate) {
  elements.sourcesList.querySelectorAll("input").forEach((input) => {
    const source = configuredSources.find((item) => item.code === input.value);
    input.checked = Boolean(source) && predicate(source);
  });
}

async function showSourcesPicker(show) {
  elements.sourcesPicker.hidden = !show;
  elements.sourcesButton.setAttribute("aria-expanded", String(show));
  if (show && (await loadConfiguredSources())) {
    if (!elements.sourcesList.children.length) renderSourcesPicker();
    elements.sourcesStatus.textContent = "";
  }
}

async function startQuickSearch() {
  if (!(await loadConfiguredSources())) {
    elements.liveStatus.textContent = "Não foi possível listar os portais de TI.";
    return;
  }
  const tech = configuredSources.filter((source) => source.tech_focus).map((source) => source.code);
  await startSearch(tech.length ? tech : null);
}

async function startSelectedSearch() {
  const sources = pickedSources();
  if (!sources.length) {
    elements.sourcesStatus.textContent = "Marque ao menos um portal.";
    return;
  }
  const all = sources.length === configuredSources.length;
  showSourcesPicker(false);
  await startSearch(all ? null : sources);
}

async function startSearch(sources = null) {
  elements.searchButton.disabled = true;
  elements.quickSearchButton.disabled = true;
  elements.liveStatus.textContent = "Iniciando busca…";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sources ? { sources } : {}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    await refreshState();
  } catch (error) {
    elements.liveStatus.textContent = `Não foi possível iniciar: ${error.message}`;
    elements.searchButton.disabled = false;
    elements.quickSearchButton.disabled = false;
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
    const period = elements.linkedinPeriod.value;
    const url = period === "week"
      ? "/api/linkedin-searches"
      : `/api/linkedin-searches?period=${encodeURIComponent(period)}`;
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const linksByTerm = new Map((payload.links ?? []).map((item) => [item.term, item.locations]));
    const terms = (payload.searches ?? []).map((search) => {
      const row = document.createElement("div");
      row.className = "linkedin-term";
      row.appendChild(textElement("span", "", search.label));
      const openers = document.createElement("span");
      openers.className = "linkedin-open";
      for (const location of linksByTerm.get(search.label) ?? []) {
        const link = document.createElement("a");
        link.href = location.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = (payload.links?.[0]?.locations?.length ?? 0) > 1
          ? `Abrir · ${location.label}`
          : "Abrir";
        link.title = `Buscar "${search.label}" em ${location.label}`;
        openers.appendChild(link);
      }
      row.appendChild(openers);
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

const EXPORT_PRESETS = {
  best: { match: "ready", minScore: 70, age: "30", tracked: "active" },
  fit: { match: "fit", minScore: 0, age: "60", tracked: "active" },
  new: { match: "fit", minScore: 0, age: "", tracked: "new" },
  all: { match: "", minScore: 0, age: "", tracked: "active" },
};
let exportCountTimer = null;

function checkedExport(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((box) => box.value);
}

function exportQuery() {
  const parameters = new URLSearchParams();
  if (elements.exportMatch.value) parameters.set("match", elements.exportMatch.value);
  const minScore = Number(elements.exportMinScore.value);
  if (minScore > 0) parameters.set("min_score", String(Math.min(100, Math.floor(minScore))));
  if (elements.exportAge.value) parameters.set("max_age_days", elements.exportAge.value);
  if (elements.exportTracked.value) parameters.set("tracked", elements.exportTracked.value);
  if (elements.exportSource.value) parameters.set("source", elements.exportSource.value);
  const levels = checkedExport("export-level");
  if (levels.length) parameters.set("levels", levels.join(","));
  const workplaces = checkedExport("export-workplace");
  if (workplaces.length) parameters.set("workplaces", workplaces.join(","));
  return parameters.toString();
}

function refreshExportLinks() {
  const query = exportQuery();
  const suffix = query ? `?${query}` : "";
  elements.exportXlsx.href = `/api/export/xlsx${suffix}`;
  elements.exportAi.href = `/api/export/ai${suffix}`;
  elements.exportCsv.href = `/api/export/csv${suffix}`;
  elements.exportMd.href = `/api/export/markdown${suffix}`;
  elements.exportCount.textContent = "Calculando…";
  clearTimeout(exportCountTimer);
  exportCountTimer = setTimeout(async () => {
    try {
      const response = await fetch(`/api/export/count${suffix}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      elements.exportCount.textContent = payload.count === 1
        ? "1 vaga será exportada."
        : `${payload.count} vagas serão exportadas.`;
      elements.exportXlsx.classList.toggle("is-disabled", payload.count === 0);
    } catch (error) {
      elements.exportCount.textContent = `Não foi possível contar: ${error.message}`;
    }
  }, 200);
}

function applyExportPreset(name) {
  const preset = EXPORT_PRESETS[name];
  if (!preset) return;
  elements.exportMatch.value = preset.match;
  elements.exportMinScore.value = String(preset.minScore);
  elements.exportAge.value = preset.age;
  elements.exportTracked.value = preset.tracked;
  document.querySelectorAll("[data-preset]").forEach((chip) =>
    chip.setAttribute("aria-pressed", String(chip.dataset.preset === name))
  );
  refreshExportLinks();
}

function showExport(show) {
  elements.exportPanel.hidden = !show;
  elements.exportButton.setAttribute("aria-expanded", String(show));
  if (!show) return;
  const selected = elements.exportSource.value;
  const sources = new Set((dashboardState.jobs ?? []).map((job) => job.source).filter(Boolean));
  elements.exportSource.replaceChildren(
    new Option("Todos os portais", ""),
    ...[...sources].sort().map((source) => new Option(source, source))
  );
  elements.exportSource.value = sources.has(selected) ? selected : "";
  refreshExportLinks();
}

async function importLinkedinText() {
  const text = elements.linkedinImportText.value.trim();
  if (!text) {
    elements.linkedinImportStatus.textContent = "Cole links, texto de alerta ou CSV primeiro.";
    return;
  }
  elements.linkedinImportButton.disabled = true;
  elements.linkedinImportStatus.textContent = "Importando…";
  try {
    const result = await profileRequest("/api/linkedin/import", { text });
    const parts = [`${result.added} nova(s)`];
    if (result.updated) parts.push(`${result.updated} atualizada(s)`);
    if (result.skipped) parts.push(`${result.skipped} já estavam na lista`);
    if (result.ignored) parts.push(`${result.ignored} link(s) ignorado(s)`);
    elements.linkedinImportStatus.textContent = result.found
      ? `Importado: ${parts.join(" · ")}.`
      : "Nenhum link de vaga do LinkedIn encontrado no texto.";
    if (result.added || result.updated) {
      elements.linkedinImportText.value = "";
      await refreshState();
    }
  } catch (error) {
    elements.linkedinImportStatus.textContent = `Não foi possível importar: ${error.message}`;
  } finally {
    elements.linkedinImportButton.disabled = false;
  }
}

function fillPreferencesForm(payload) {
  elements.searchTerms.value = (payload.search_terms ?? []).join("\n");
  elements.locationScopes.value = (payload.location_scopes ?? []).join("\n");
  elements.technologies.value = (payload.technologies ?? []).join("\n");
  elements.excludedTerms.value = (payload.excluded_terms ?? []).join("\n");
  const levels = payload.seniority_levels ?? [];
  [
    elements.seniorityInternship,
    elements.seniorityJunior,
    elements.seniorityMid,
    elements.senioritySenior,
  ].forEach((box) => setChecked(box, levels));
  const models = payload.workplace_models ?? [];
  [elements.workplaceRemote, elements.workplaceHybrid, elements.workplaceOnsite].forEach(
    (box) => setChecked(box, models)
  );
}

const SENIORITY_BOXES = () => [
  elements.seniorityInternship,
  elements.seniorityJunior,
  elements.seniorityMid,
  elements.senioritySenior,
];

let presetsState = null;
const selectedStacks = new Set();

async function loadPresets() {
  if (presetsState) return;
  try {
    const response = await fetch("/api/presets", { cache: "no-store" });
    presetsState = await response.json();
    elements.stackChips.replaceChildren(
      ...presetsState.stacks.map((stack) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.dataset.stack = stack.id;
        chip.setAttribute("aria-pressed", "false");
        chip.textContent = stack.label;
        chip.addEventListener("click", () => {
          const on = !selectedStacks.has(stack.id);
          if (on) selectedStacks.add(stack.id);
          else selectedStacks.delete(stack.id);
          chip.setAttribute("aria-pressed", String(on));
          chip.classList.toggle("chip-on", on);
        });
        return chip;
      })
    );
  } catch (error) {
    elements.stackChips.textContent = `Não foi possível carregar as stacks: ${error.message}`;
  }
}

async function applySuggestions() {
  const levels = checkedValues(SENIORITY_BOXES());
  if (selectedStacks.size === 0) {
    elements.preferencesStatus.textContent = "Marque ao menos uma stack para receber sugestões.";
    return;
  }
  const query = new URLSearchParams({
    stacks: [...selectedStacks].join(","),
    levels: levels.join(","),
  });
  try {
    const response = await fetch(`/api/presets/suggest?${query}`, { cache: "no-store" });
    const suggestion = await response.json();
    if (!response.ok) throw new Error(suggestion.error || `HTTP ${response.status}`);
    elements.technologies.value = suggestion.technologies.join("\n");
    elements.searchTerms.value = suggestion.search_terms.join("\n");
    elements.preferencesStatus.textContent =
      "Sugestões preenchidas. Ajuste se quiser e clique em Salvar configurações.";
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível sugerir: ${error.message}`;
  }
}

function currentPreferencesPayload() {
  return {
    search_terms: linesFrom(elements.searchTerms),
    seniority_levels: checkedValues(SENIORITY_BOXES()),
    workplace_models: checkedValues([
      elements.workplaceRemote,
      elements.workplaceHybrid,
      elements.workplaceOnsite,
    ]),
    location_scopes: linesFrom(elements.locationScopes),
    technologies: linesFrom(elements.technologies),
    excluded_terms: linesFrom(elements.excludedTerms),
  };
}

function renderProfiles(payload) {
  const active = payload.active ?? "";
  const options = [
    new Option("Perfil atual (sem nome)", ""),
    ...(payload.profiles ?? []).map((profile) => new Option(profile.name, profile.name)),
  ];
  elements.profileSelect.replaceChildren(...options);
  elements.profileSelect.value = active;
  elements.profileDelete.disabled = !elements.profileSelect.value;
}

async function loadProfiles() {
  try {
    const response = await fetch("/api/profiles", { cache: "no-store" });
    renderProfiles(await response.json());
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível listar perfis: ${error.message}`;
  }
}

async function profileRequest(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function saveProfile() {
  const name = elements.profileName.value.trim() || elements.profileSelect.value;
  if (!name) {
    elements.preferencesStatus.textContent = "Digite um nome para salvar o perfil.";
    return;
  }
  const preferences = currentPreferencesPayload();
  if (preferences.seniority_levels.length === 0 || preferences.location_scopes.length === 0) {
    elements.preferencesStatus.textContent = "Marque ao menos um nível e informe uma localidade.";
    return;
  }
  try {
    const payload = await fetch("/api/profiles", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, preferences }),
    }).then(async (response) => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    });
    renderProfiles(payload);
    linkedinLoaded = false;
    elements.profileName.value = "";
    elements.preferencesStatus.textContent = `Perfil "${name}" salvo e ativado.`;
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível salvar o perfil: ${error.message}`;
  }
}

async function switchProfile() {
  const name = elements.profileSelect.value;
  elements.profileDelete.disabled = !name;
  if (!name) return;
  try {
    const payload = await profileRequest("/api/profiles/activate", { name });
    renderProfiles(payload);
    fillPreferencesForm(payload.preferences ?? {});
    linkedinLoaded = false;
    elements.preferencesStatus.textContent = `Perfil "${name}" ativado. Clique em Buscar vagas agora.`;
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível ativar: ${error.message}`;
  }
}

async function deleteProfile() {
  const name = elements.profileSelect.value;
  if (!name || !window.confirm(`Excluir o perfil "${name}"?`)) return;
  try {
    renderProfiles(await profileRequest("/api/profiles/delete", { name }));
    elements.preferencesStatus.textContent = `Perfil "${name}" excluído.`;
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível excluir: ${error.message}`;
  }
}

function applyRulesToForm(rules) {
  elements.ruleOffTopic.checked = rules.off_topic !== false;
  elements.ruleExcluded.checked = rules.excluded !== false;
  elements.ruleExpired.checked = rules.expired !== false;
  elements.ruleAge.value = rules.max_age_days ? String(rules.max_age_days) : "";
}

async function loadCleanupRules() {
  try {
    const response = await fetch("/api/cleanup/rules", { cache: "no-store" });
    applyRulesToForm(await response.json());
  } catch (error) {
    elements.rulesStatus.textContent = `Não foi possível carregar as regras: ${error.message}`;
  }
}

async function saveCleanupRules() {
  elements.rulesStatus.textContent = "Salvando…";
  try {
    const response = await fetch("/api/cleanup/rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        off_topic: elements.ruleOffTopic.checked,
        excluded: elements.ruleExcluded.checked,
        expired: elements.ruleExpired.checked,
        max_age_days: elements.ruleAge.value ? Number(elements.ruleAge.value) : null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    elements.rulesStatus.textContent = "Regras salvas — valem a partir da próxima coleta.";
  } catch (error) {
    elements.rulesStatus.textContent = `Não foi possível salvar as regras: ${error.message}`;
  }
}

function renderBreakdown(result) {
  const labels = result.removed_labels ?? {};
  const items = Object.entries(result.removed ?? {}).map(([reason, count]) => {
    const item = document.createElement("li");
    item.appendChild(textElement("strong", "", String(count)));
    item.appendChild(document.createTextNode(` ${labels[reason] ?? reason}`));
    return item;
  });
  elements.cleanupBreakdown.replaceChildren(...items);
  const samples = (result.samples ?? []).map((sample) => {
    const item = document.createElement("li");
    item.appendChild(document.createTextNode(sample.title));
    item.appendChild(textElement(
      "small", "", [sample.company, sample.source, sample.reason].filter(Boolean).join(" · ")
    ));
    return item;
  });
  const total = Object.values(result.removed ?? {}).reduce((sum, n) => sum + n, 0);
  if (total > samples.length) {
    samples.push(textElement("li", "", `… e mais ${total - samples.length} vagas.`));
  }
  elements.cleanupSamples.replaceChildren(...samples);
}

function renderBackup(backup) {
  elements.undoBox.hidden = !backup;
  if (!backup) return;
  const when = new Date(backup.at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  elements.undoInfo.textContent =
    `Última limpeza em ${when}: ${backup.jobs} vagas removidas podem voltar para a lista.`;
}

function cleanupBody(dryRun) {
  return { dry_run: dryRun, remove_discarded: elements.cleanupDiscarded.checked };
}

async function refreshCleanupOverview() {
  try {
    const result = await profileRequest("/api/cleanup", cleanupBody(true));
    const removable = Object.values(result.removed ?? {}).reduce((sum, n) => sum + n, 0);
    elements.cleanupOverview.replaceChildren(
      document.createTextNode(`Na lista: ${result.before} vagas. `),
      removable
        ? textElement("strong", "", `${removable} seriam removidas agora`)
        : document.createTextNode("Nada para limpar agora — a lista está em ordem.")
    );
    renderBreakdown(result);
    renderBackup(result.backup);
    return result;
  } catch (error) {
    elements.cleanupOverview.textContent = `Não foi possível calcular: ${error.message}`;
    return null;
  }
}

async function showCleanup(show) {
  elements.cleanupPanel.hidden = !show;
  elements.cleanupButton.setAttribute("aria-expanded", String(show));
  if (!show) return;
  elements.cleanupOverview.textContent = "Calculando…";
  await Promise.all([loadCleanupRules(), refreshCleanupOverview()]);
}

async function runCleanup(dryRun) {
  if (dryRun) {
    elements.cleanupStatus.textContent = "Calculando…";
    const result = await refreshCleanupOverview();
    if (result) {
      const removed = Object.values(result.removed ?? {}).reduce((sum, n) => sum + n, 0);
      elements.cleanupStatus.textContent = `${removed} de ${result.before} vagas seriam removidas.`;
    } else {
      elements.cleanupStatus.textContent = "";
    }
    return;
  }
  if (!window.confirm("Remover as vagas listadas na prévia? Você poderá desfazer logo em seguida.")) {
    return;
  }
  elements.cleanupStatus.textContent = "Limpando…";
  try {
    const result = await profileRequest("/api/cleanup", cleanupBody(false));
    const removed = Object.values(result.removed ?? {}).reduce((sum, n) => sum + n, 0);
    elements.cleanupStatus.textContent = `${removed} removidas. Restam ${result.after} vagas.`;
    await refreshState();
    await refreshCleanupOverview();
  } catch (error) {
    elements.cleanupStatus.textContent = `Não foi possível limpar: ${error.message}`;
  }
}

async function undoCleanup() {
  elements.cleanupStatus.textContent = "Desfazendo…";
  try {
    const result = await profileRequest("/api/cleanup/undo", {});
    elements.cleanupStatus.textContent = `${result.restored} vagas devolvidas. A lista tem ${result.total} vagas.`;
    await refreshState();
    await refreshCleanupOverview();
  } catch (error) {
    elements.cleanupStatus.textContent = `Não foi possível desfazer: ${error.message}`;
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
    fillPreferencesForm(payload);
    preferencesLoaded = true;
    elements.preferencesStatus.textContent = "Configurações atuais carregadas.";
    await Promise.all([loadPresets(), loadProfiles()]);
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
  const payload = currentPreferencesPayload();
  if (payload.seniority_levels.length === 0) {
    elements.preferencesStatus.textContent = "Selecione ao menos um nível.";
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

elements.searchButton.addEventListener("click", () => startSearch());
elements.quickSearchButton.addEventListener("click", startQuickSearch);
elements.sourcesButton.addEventListener("click", () => showSourcesPicker(elements.sourcesPicker.hidden));
elements.closeSources.addEventListener("click", () => showSourcesPicker(false));
elements.selectTech.addEventListener("click", () => setPicked((source) => source.tech_focus));
elements.selectAll.addEventListener("click", () => setPicked(() => true));
elements.searchSelected.addEventListener("click", startSelectedSearch);
elements.showMore.addEventListener("click", () => {
  visibleRows += ROW_PAGE_SIZE;
  renderTable();
});
elements.preferencesButton.addEventListener("click", async () => {
  const willShow = elements.preferencesPanel.hidden;
  showPreferences(willShow);
  if (willShow) await loadPreferences();
});
elements.closePreferences.addEventListener("click", () => showPreferences(false));
elements.preferencesForm.addEventListener("submit", savePreferences);
elements.applySuggestions.addEventListener("click", applySuggestions);
elements.profileSave.addEventListener("click", saveProfile);
elements.profileSelect.addEventListener("change", switchProfile);
elements.profileDelete.addEventListener("click", deleteProfile);
[elements.ruleOffTopic, elements.ruleExcluded, elements.ruleExpired, elements.ruleAge].forEach(
  (control) => control.addEventListener("change", saveCleanupRules)
);
elements.cleanupPreview.addEventListener("click", () => runCleanup(true));
elements.cleanupButton.addEventListener("click", () => showCleanup(elements.cleanupPanel.hidden));
elements.closeCleanup.addEventListener("click", () => showCleanup(false));
elements.cleanupUndo.addEventListener("click", undoCleanup);
elements.cleanupDiscarded.addEventListener("change", refreshCleanupOverview);
elements.cleanupRun.addEventListener("click", () => runCleanup(false));
document.querySelectorAll("[data-location]").forEach((chip) => {
  chip.addEventListener("click", () => {
    const current = linesFrom(elements.locationScopes);
    if (!current.includes(chip.dataset.location)) current.push(chip.dataset.location);
    elements.locationScopes.value = current.join("\n");
  });
});
elements.linkedinButton.addEventListener("click", async () => {
  const willShow = elements.linkedinPanel.hidden;
  showLinkedin(willShow);
  if (willShow) await loadLinkedinSearches();
});
elements.closeLinkedin.addEventListener("click", () => showLinkedin(false));
elements.exportButton.addEventListener("click", () => showExport(elements.exportPanel.hidden));
elements.closeExport.addEventListener("click", () => showExport(false));
document.querySelectorAll("[data-preset]").forEach((chip) =>
  chip.addEventListener("click", () => applyExportPreset(chip.dataset.preset))
);
[
  elements.exportMatch, elements.exportMinScore, elements.exportAge,
  elements.exportTracked, elements.exportSource,
  ...document.querySelectorAll('input[name="export-level"], input[name="export-workplace"]'),
].forEach((control) =>
  control.addEventListener("change", () => {
    document.querySelectorAll("[data-preset]").forEach((chip) => chip.setAttribute("aria-pressed", "false"));
    refreshExportLinks();
  })
);
elements.linkedinPeriod.addEventListener("change", () => {
  linkedinLoaded = false;
  loadLinkedinSearches();
});
elements.linkedinImportButton.addEventListener("click", importLinkedinText);
[
  elements.textFilter,
  elements.sourceFilter,
  elements.matchFilter,
  elements.sortOrder,
  elements.trackingFilter,
].forEach((filter) => {
  const rerender = () => {
    visibleRows = ROW_PAGE_SIZE;
    renderTable();
  };
  filter.addEventListener("input", rerender);
  filter.addEventListener("change", () => { saveFilters(); rerender(); });
});
elements.clearFilters.addEventListener("click", resetFilters);
[[elements.cardAll, ""], [elements.cardReady, "ready"]].forEach(([card, match]) => {
  card.addEventListener("click", () => focusResults(match));
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); focusResults(match); }
  });
});
document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName ?? "");
  if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    elements.textFilter.focus();
  } else if (event.key === "Escape") {
    [showExport, showLinkedin, showPreferences, showCleanup].forEach((close) => close(false));
    if (!elements.sourcesPicker.hidden) showSourcesPicker(false);
    if (document.activeElement === elements.textFilter && elements.textFilter.value) {
      elements.textFilter.value = "";
      resetFilters();
    }
  }
});
elements.toggleSources.addEventListener("click", () => {
  const willShow = elements.sourceStatuses.hidden;
  elements.sourceStatuses.hidden = !willShow;
  elements.toggleSources.textContent = willShow ? "Ocultar detalhes" : "Ver detalhes";
});

restoreFilters();
refreshState();
loadTracking();

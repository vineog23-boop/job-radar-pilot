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
  requiredKeywords: document.querySelector("#required-keywords"),
  bonusKeywords: document.querySelector("#bonus-keywords"),
  blockedKeywords: document.querySelector("#blocked-keywords"),
  excludedCompanies: document.querySelector("#excluded-companies"),
  favoriteCompanies: document.querySelector("#favorite-companies"),
  contractBoxes: [...document.querySelectorAll("#contract-clt, #contract-pj, #contract-freelance")],
  avoidEnglish: document.querySelector("#avoid-english"),
  reapplySaved: document.querySelector("#reapply-saved"),
  previewPreferences: document.querySelector("#preview-preferences"),
  preferencesImpact: document.querySelector("#preferences-impact"),
  searchTermsCount: document.querySelector("#search-terms-count"),
  termsEstimate: document.querySelector("#terms-estimate"),
  termsBuilderToggle: document.querySelector("#terms-builder-toggle"),
  termsBuilder: document.querySelector("#terms-builder"),
  termsGroups: document.querySelector("#terms-groups"),
  termsSelectedCount: document.querySelector("#terms-selected-count"),
  termsRecommended: document.querySelector("#terms-recommended"),
  termsClear: document.querySelector("#terms-clear"),
  termsAdd: document.querySelector("#terms-add"),
  termsReplace: document.querySelector("#terms-replace"),
  termsStatus: document.querySelector("#terms-status"),
  suggestMerge: document.querySelector("#suggest-merge"),
  newStackToggle: document.querySelector("#new-stack-toggle"),
  newStackForm: document.querySelector("#new-stack-form"),
  newStackLabel: document.querySelector("#new-stack-label"),
  newStackTechs: document.querySelector("#new-stack-techs"),
  newStackQueries: document.querySelector("#new-stack-queries"),
  newStackSave: document.querySelector("#new-stack-save"),
  newStackCancel: document.querySelector("#new-stack-cancel"),
  newStackStatus: document.querySelector("#new-stack-status"),
  techInsights: document.querySelector("#tech-insights"),
  techInsightsChips: document.querySelector("#tech-insights-chips"),
  companyInsights: document.querySelector("#company-insights"),
  seniorityInternship: document.querySelector("#seniority-internship"),
  seniorityJunior: document.querySelector("#seniority-junior"),
  workplaceRemote: document.querySelector("#workplace-remote"),
  workplaceHybrid: document.querySelector("#workplace-hybrid"),
  workplaceOnsite: document.querySelector("#workplace-onsite"),
  downloadReport: document.querySelector("#download-report"),
  clearFilters: document.querySelector("#clear-filters"),
  runControls: document.querySelector("#run-controls"),
  pauseButton: document.querySelector("#pause-button"),
  stopButton: document.querySelector("#stop-button"),
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
  autoExportEnabled: document.querySelector("#auto-export-enabled"),
  autoExportFolder: document.querySelector("#auto-export-folder"),
  autoExportSave: document.querySelector("#auto-export-save"),
  autoExportOpen: document.querySelector("#auto-export-open"),
  autoExportRun: document.querySelector("#auto-export-run"),
  autoExportStatus: document.querySelector("#auto-export-status"),
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
  newsBanner: document.querySelector("#news-banner"),
  newsText: document.querySelector("#news-text"),
  newsShow: document.querySelector("#news-show"),
  newsDismiss: document.querySelector("#news-dismiss"),
  quickChips: [...document.querySelectorAll("[data-quick]")],
  toast: document.querySelector("#toast"),
  toastText: document.querySelector("#toast-text"),
  toastUndo: document.querySelector("#toast-undo"),
  funnel: document.querySelector("#funnel"),
};

const FILTER_KEY = "radar.filters";
const FILTER_DEFAULTS = { match: "", sort: "fit", tracked: "active" };
const expandedJobs = new Set();
// Filtros rápidos (chips): somam aos selects.
const QUICK_FILTERS = ["unseen", "remote", "estagio", "junior", "recent"];
const quickFilters = new Set();

// Vagas que a pessoa já viu (abriu, expandiu ou marcou como vistas), só neste navegador.
const SEEN_KEY = "radar.seen.v1";
const MAX_SEEN = 20000;
const seen = loadSeen();

function loadSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    if (raw === null) return { known: false, urls: new Set() };
    const urls = JSON.parse(raw);
    return { known: true, urls: new Set(Array.isArray(urls) ? urls : []) };
  } catch (error) {
    return { known: false, urls: new Set() };
  }
}

function saveSeen() {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen.urls].slice(-MAX_SEEN)));
  } catch (error) { /* armazenamento indisponível */ }
}

function markSeen(urls) {
  let changed = !seen.known;
  urls.filter(Boolean).forEach((url) => {
    if (!seen.urls.has(url)) { seen.urls.add(url); changed = true; }
  });
  seen.known = true;
  if (changed) saveSeen();
}

// Antes da primeira marcação, "não vista" = nova na última coleta (STATUS:NEW).
function isUnseen(job) {
  if (!seen.known) return (job.match_labels ?? []).includes("STATUS:NEW");
  return !seen.urls.has(job.canonical_url);
}

function saveFilters() {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify({
      match: elements.matchFilter.value,
      sort: elements.sortOrder.value,
      tracked: elements.trackingFilter.value,
      quick: [...quickFilters],
    }));
  } catch (error) { /* armazenamento indisponível: segue sem lembrar */ }
}

function syncQuickChips() {
  elements.quickChips.forEach((chip) =>
    chip.setAttribute("aria-pressed", String(quickFilters.has(chip.dataset.quick)))
  );
}

function hasLevel(job, level) {
  const labels = (job.match_labels ?? []).map(String);
  return labels.includes(`SENIORITY_MATCH:${level}`) || normalized(job.seniority ?? "") === level;
}

function isRemoteJob(job) {
  const labels = (job.match_labels ?? []).map(String);
  return job.workplace_model === "REMOTE"
    || labels.includes("WORKPLACE_MATCH:REMOTE")
    || labels.includes("LOCATION_MATCH:remote_brazil");
}

function passesQuickFilters(job) {
  if (quickFilters.has("unseen") && !isUnseen(job)) return false;
  if (quickFilters.has("remote") && !isRemoteJob(job)) return false;
  const levels = ["estagio", "junior"].filter((level) => quickFilters.has(level));
  if (levels.length && !levels.some((level) => hasLevel(job, level))) return false;
  if (quickFilters.has("recent")) {
    const published = publishedTime(job);
    if (published === -Infinity || Date.now() - published > 7 * 86400000) return false;
  }
  return true;
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
    (Array.isArray(saved.quick) ? saved.quick : [])
      .filter((name) => QUICK_FILTERS.includes(name))
      .forEach((name) => quickFilters.add(name));
  } catch (error) { /* valor salvo inválido: ignora */ }
  syncQuickChips();
}

function filtersAreDefault() {
  return !elements.textFilter.value.trim()
    && !elements.sourceFilter.value
    && elements.matchFilter.value === FILTER_DEFAULTS.match
    && elements.sortOrder.value === FILTER_DEFAULTS.sort
    && elements.trackingFilter.value === FILTER_DEFAULTS.tracked
    && quickFilters.size === 0;
}

function resetFilters() {
  elements.textFilter.value = "";
  elements.sourceFilter.value = "";
  elements.matchFilter.value = FILTER_DEFAULTS.match;
  elements.sortOrder.value = FILTER_DEFAULTS.sort;
  elements.trackingFilter.value = FILTER_DEFAULTS.tracked;
  quickFilters.clear();
  syncQuickChips();
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
  ["KEYWORD_MATCH:", "Obrigatória"],
  ["BONUS_MATCH:", "Diferencial"],
  ["COMPANY_FAVORITE:", "Empresa favorita"],
  ["CONTRACT:", "Contrato"],
];

// Diferenciais (+5 cada, até 10) e empresa favorita (+10) entram no score e no ranking.
function boostPoints(job) {
  const labels = (job.match_labels ?? []).map(String);
  const bonus = labels.filter((label) => label.startsWith("BONUS_MATCH:")).length;
  const favorite = labels.some((label) => label.startsWith("COMPANY_FAVORITE:"));
  return Math.min(10, bonus * 5) + (favorite ? 10 : 0);
}

function jobScore(job) {
  const state = fitState(job);
  const points = fitScore(job);
  if (state === "EXCLUDE" || points < 0 || !Number.isFinite(points)) return 0;
  let score = points * 20 + (state === "READY" ? 10 : 0) + boostPoints(job);
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
  const reposted = (job.match_labels ?? []).map(String).find((label) => label.startsWith("REPOSTED:"));
  if (reposted) facts.push(`Republicada ${reposted.slice(9)}× neste portal (mostramos o anúncio mais recente)`);
  if (job.employment_type) facts.push(`Contrato: ${job.employment_type}`);
  if (publishedLabel(job)) facts.push(`Publicada em ${publishedLabel(job)}`);
  const list = document.createElement("ul");
  list.className = "detail-facts";
  facts.forEach((fact) => list.appendChild(textElement("li", "", fact)));
  box.appendChild(list);
  const techs = document.createElement("div");
  techs.className = "detail-techs";
  jobTechnologies(job).forEach((tech) => techs.appendChild(textElement("span", "tech-chip", tech)));
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
  ["TITLE_EXCLUDED:", "cargo com um termo que você não quer"],
  ["KEYWORD_BLOCKED:", "cita uma palavra proibida"],
  ["KEYWORD_MISSING:", "não cita nenhuma palavra obrigatória"],
  ["COMPANY_EXCLUDED:", "empresa que você quer evitar"],
  ["CONTRACT_MISMATCH:", "tipo de contrato diferente"],
  ["LANGUAGE_MISMATCH:", "exige inglês avançado"],
];

// Tecnologias do portal + as que o classificador achou (rótulos TECH_MATCH:).
function jobTechnologies(job) {
  const matched = (job.match_labels ?? [])
    .map(String)
    .filter((label) => label.startsWith("TECH_MATCH:"))
    .map((label) => label.slice("TECH_MATCH:".length))
    .sort();
  const seen = new Set();
  return [...(job.technologies ?? []).map(String), ...matched].filter((tech) => {
    const key = tech.toLowerCase();
    if (!tech || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function isOffTopic(job) {
  return (job.match_labels ?? []).includes("RELEVANCE:OFF_TOPIC");
}

function fitReasons(job) {
  const labels = (job.match_labels ?? []).map(String);
  const reasons = REASON_LABELS
    .filter(([prefix]) => labels.some((label) => label.startsWith(prefix)))
    .map(([, text]) => text);
  const stacks = labels.filter((label) => label.startsWith("OTHER_STACK:")).map((label) => label.slice(12));
  if (stacks.length) reasons.push(`stack diferente da sua (${stacks.join(", ")})`);
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
  ["INTERVIEW", "Entrevista"],
  ["OFFER", "Oferta"],
  ["REJECTED", "Recusada"],
  ["DISCARDED", "Descartada"],
];
const TRACKED_FILTER_STATUS = {
  saved: "SAVED",
  applied: "APPLIED",
  interview: "INTERVIEW",
  offer: "OFFER",
  rejected: "REJECTED",
  discarded: "DISCARDED",
};
const IN_PROGRESS = ["APPLIED", "INTERVIEW", "OFFER"];
let linkedinLoaded = false;

function normalized(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function fitState(job) {
  const label = (job.match_labels ?? []).find((item) =>
    /^FIT:(READY|CONDITIONAL|EXCLUDE|OTHER_STACK|AMBIGUOUS)$/.test(String(item))
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
    OTHER_STACK: "Outra stack",
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
    if (tracked === "inprogress" && !IN_PROGRESS.includes(trackedStatus)) return false;
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
    if (match === "fit" && !["READY", "CONDITIONAL"].includes(state)) return false;
    if (match === "review" && !["CONDITIONAL", "AMBIGUOUS"].includes(state)) return false;
    if (match === "otherstack" && state !== "OTHER_STACK") return false;
    if (match === "exclude" && state !== "EXCLUDE") return false;
    return passesQuickFilters(job);
  }).sort((left, right) => {
    const order = { READY: 0, CONDITIONAL: 1, AMBIGUOUS: 2, OTHER_STACK: 3, EXCLUDE: 4 };
    const byState = order[fitState(left)] - order[fitState(right)];
    const byFit =
      byState ||
      fitScore(right) - fitScore(left) ||
      boostPoints(right) - boostPoints(left);
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
  renderFunnel();
}

let toastTimer;
let toastUndo = null;

function showToast(text, undo) {
  window.clearTimeout(toastTimer);
  elements.toastText.textContent = text;
  toastUndo = undo;
  elements.toastUndo.hidden = !undo;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => { elements.toast.hidden = true; toastUndo = null; }, 8000);
}

const TRACKING_NAMES = Object.fromEntries(TRACKING_OPTIONS.filter(([value]) => value));

async function updateTracking(job, status, select, { undoable = true } = {}) {
  const previous = trackingStatus(job);
  select.disabled = true;
  let saved = false;
  try {
    const response = await fetch("/api/tracking", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: job.canonical_url, status: status || null }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    trackingState = payload.jobs ?? {};
    saved = true;
  } catch (error) {
    elements.liveStatus.textContent = `Não foi possível salvar o acompanhamento: ${error.message}`;
  } finally {
    select.disabled = false;
    markSeen([job.canonical_url]);
    renderTable();
    renderNews();
    renderFunnel();
  }
  if (saved && undoable && previous !== status) {
    const name = TRACKING_NAMES[status] || "sem acompanhamento";
    const hidden = status === "DISCARDED" && elements.trackingFilter.value === "active";
    showToast(
      `"${job.title || "Vaga"}" marcada como ${name}${hidden ? " (some da lista)" : ""}.`,
      () => updateTracking(job, previous, select, { undoable: false })
    );
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
          jobTechnologies(job).slice(0, 4).join(" · ") || "Tecnologias não informadas",
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
      else {
        expandedJobs.add(job.canonical_url);
        markSeen([job.canonical_url]);
        renderNews();
      }
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
    if (isUnseen(job)) {
      matchCell.appendChild(textElement("span", "match-pill new", "Nova"));
      row.classList.add("unseen");
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
    link.addEventListener("click", () => { markSeen([job.canonical_url]); renderNews(); });
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
        `${source.records ?? 0} registros · ${source.stop_reason === "STOPPED_BY_USER" ? "interrompido por você" : source.stop_reason || "concluído"}`
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
  elements.searchButton.classList.toggle("running", running && !dashboardState.paused);
  elements.runControls.hidden = !running;
  elements.pauseButton.textContent = dashboardState.paused ? "▶ Retomar busca" : "⏸ Pausar busca";
  elements.pauseButton.disabled = Boolean(dashboardState.stopping);
  elements.stopButton.disabled = Boolean(dashboardState.stopping);
  const messages = {
    IDLE: "Resultados locais carregados.",
    RUNNING: "Buscando vagas… acompanhe os portais abaixo.",
    DONE: "Busca concluída com sucesso.",
    PARTIAL: "Busca concluída; alguns portais exigem atenção.",
    STOPPED: "Busca interrompida. O que já tinha sido encontrado foi salvo.",
    ERROR: dashboardState.error || "A busca encontrou um erro.",
  };
  let message = messages[dashboardState.status] || "Painel pronto.";
  if (running && dashboardState.stopping) {
    message = "Encerrando… terminando a consulta atual e salvando as vagas.";
  } else if (running && dashboardState.paused) {
    message = "Busca pausada. Nenhuma página nova é consultada até você retomar.";
  }
  const exports = dashboardState.exports ?? [];
  if (!running && exports.length) {
    message += ` Planilha salva em ${exports[exports.length - 1]}.`;
  }
  elements.liveStatus.textContent = dashboardState.read_error
    ? `Não foi possível ler a saída: ${dashboardState.read_error}`
    : message;
}

async function controlSearch(action) {
  if (action === "stop" && !window.confirm("Parar a busca agora? As vagas já encontradas serão salvas.")) {
    return;
  }
  elements.pauseButton.disabled = true;
  elements.stopButton.disabled = true;
  try {
    const response = await fetch(`/api/search/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    Object.assign(dashboardState, payload);
    renderRunState();
  } catch (error) {
    elements.liveStatus.textContent = `Não foi possível ${action === "stop" ? "parar" : "pausar"}: ${error.message}`;
  }
  await refreshState();
}

// Funil de candidatura (todas as vagas acompanhadas, não só as da lista atual).
const FUNNEL_STAGES = [
  ["SAVED", "salva", "salvas", "saved"],
  ["APPLIED", "aplicada", "aplicadas", "applied"],
  ["INTERVIEW", "entrevista", "entrevistas", "interview"],
  ["OFFER", "oferta", "ofertas", "offer"],
  ["REJECTED", "recusada", "recusadas", "rejected"],
];

function setTrackingFilter(value) {
  elements.trackingFilter.value = value;
  saveFilters();
  visibleRows = ROW_PAGE_SIZE;
  renderTable();
}

function renderFunnel() {
  const counts = {};
  Object.values(trackingState).forEach((entry) => {
    counts[entry.status] = (counts[entry.status] ?? 0) + 1;
  });
  const total = FUNNEL_STAGES.reduce((sum, [status]) => sum + (counts[status] ?? 0), 0);
  elements.funnel.hidden = total === 0;
  if (!total) return;
  const inProgress = IN_PROGRESS.reduce((sum, status) => sum + (counts[status] ?? 0), 0);
  const parts = FUNNEL_STAGES.map(([status, one, many, filter]) => {
    const count = counts[status] ?? 0;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "funnel-step";
    button.textContent = `${count} ${count === 1 ? one : many}`;
    button.title = `Mostrar só as vagas: ${many}`;
    button.addEventListener("click", () => setTrackingFilter(filter));
    return button;
  });
  const progress = document.createElement("button");
  progress.type = "button";
  progress.className = "chip funnel-progress";
  progress.textContent = `Em processo: ${inProgress}`;
  progress.addEventListener("click", () => setTrackingFilter("inprogress"));
  elements.funnel.replaceChildren(textElement("span", "funnel-label", "Seu funil:"), ...parts, progress);
}

// Faixa "N vagas compatíveis novas para você".
function newsJobs() {
  return (dashboardState.jobs ?? []).filter((job) =>
    !isOffTopic(job)
    && ["READY", "CONDITIONAL"].includes(fitState(job))
    && !trackingStatus(job)
    && isUnseen(job)
  );
}

function renderNews() {
  const fresh = newsJobs();
  elements.newsBanner.hidden = fresh.length === 0;
  if (!fresh.length) return;
  const ready = fresh.filter((job) => fitState(job) === "READY").length;
  const since = seen.known ? "que você ainda não viu" : "nesta última busca";
  elements.newsText.textContent =
    `${fresh.length} ${fresh.length === 1 ? "vaga compatível nova" : "vagas compatíveis novas"} ${since}` +
    (ready ? ` (${ready} mais compatíveis).` : ".");
}

function showNews() {
  elements.textFilter.value = "";
  elements.sourceFilter.value = "";
  elements.matchFilter.value = "fit";
  elements.trackingFilter.value = "active";
  quickFilters.clear();
  quickFilters.add("unseen");
  syncQuickChips();
  saveFilters();
  visibleRows = ROW_PAGE_SIZE;
  renderTable();
  elements.tableBody.closest(".workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function render() {
  updateSourceFilter();
  renderSummary();
  renderNews();
  renderTable();
  renderSources();
  renderRunState();
}

// Versão do vagas.jsonl já desenhada: o servidor só manda as vagas se ela mudou.
let outputVersion = "";

async function refreshState() {
  window.clearTimeout(refreshTimer);
  try {
    const query = outputVersion ? `?since=${encodeURIComponent(outputVersion)}` : "";
    const response = await fetch(`/api/state${query}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const fresh = await response.json();
    if (fresh.unchanged) {
      // Mesmas vagas: atualiza progresso e resumo sem recriar a tabela (mantém
      // o foco do teclado e as linhas expandidas).
      dashboardState = {
        ...fresh,
        jobs: dashboardState.jobs,
        report: dashboardState.report,
        read_error: dashboardState.read_error,
      };
      renderSummary();
      renderSources();
      renderRunState();
    } else {
      dashboardState = fresh;
      render();
    }
    outputVersion = fresh.output_version || "";
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
  loadAutoExport();
}

// --- Exportação automática (pasta do usuário, ao fim de cada busca) ---
async function autoExportRequest(path, method, body) {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function loadAutoExport() {
  try {
    const settings = await autoExportRequest("/api/auto-export", "GET");
    elements.autoExportEnabled.checked = settings.enabled;
    elements.autoExportFolder.value = settings.folder;
  } catch (error) {
    elements.autoExportStatus.textContent = `Não foi possível ler a configuração: ${error.message}`;
  }
}

async function saveAutoExport() {
  try {
    const settings = await autoExportRequest("/api/auto-export", "PUT", {
      enabled: elements.autoExportEnabled.checked,
      folder: elements.autoExportFolder.value.trim(),
    });
    elements.autoExportFolder.value = settings.folder;
    elements.autoExportStatus.textContent = settings.enabled
      ? `Ligada: cada busca salva as planilhas em ${settings.folder}.`
      : "Desligada: as buscas não geram planilhas sozinhas.";
  } catch (error) {
    elements.autoExportStatus.textContent = `Não foi possível salvar: ${error.message}`;
  }
}

async function runAutoExport() {
  elements.autoExportStatus.textContent = "Exportando…";
  try {
    const result = await autoExportRequest("/api/auto-export/run", "POST", {});
    elements.autoExportStatus.textContent = result.files.length
      ? `Pronto: ${result.files.length} arquivos em ${result.folder}.`
      : "Ainda não há vagas de TI para exportar.";
  } catch (error) {
    elements.autoExportStatus.textContent = error.message;
  }
}

async function openAutoExportFolder() {
  try {
    const result = await autoExportRequest("/api/auto-export/open", "POST", {});
    elements.autoExportStatus.textContent = `Pasta aberta: ${result.folder}`;
  } catch (error) {
    elements.autoExportStatus.textContent = error.message;
  }
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

// --- campos de etiquetas (tecnologias, palavras-chave, empresas) -------------------
// O <textarea> original continua sendo a fonte do valor (uma etiqueta por linha);
// a caixa de etiquetas só desenha e edita esse valor.
const tagInputs = new Map();

function setupTagInput(textarea) {
  textarea.hidden = true;
  const box = document.createElement("div");
  box.className = "tag-input";
  const list = document.createElement("span");
  list.className = "tag-list";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "tag-entry";
  input.id = `${textarea.id}-entry`;
  input.placeholder = textarea.dataset.placeholder || "Digite e tecle Enter";
  input.setAttribute("aria-label", textarea.getAttribute("aria-label") || textarea.id);
  input.autocomplete = "off";
  box.append(list, input);
  textarea.after(box);

  const values = () => linesFrom(textarea);
  const render = () => {
    list.replaceChildren(
      ...values().map((item, index) => {
        const chip = document.createElement("span");
        chip.className = "tag";
        chip.append(document.createTextNode(item));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "tag-remove";
        remove.setAttribute("aria-label", `Remover ${item}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => {
          const items = values();
          items.splice(index, 1);
          write(items);
        });
        chip.append(remove);
        return chip;
      })
    );
  };
  const write = (items) => {
    textarea.value = items.join("\n");
    render();
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const add = (raw) => {
    const parts = String(raw).split(/[,;\n]/).map((part) => part.trim()).filter(Boolean);
    if (!parts.length) return;
    const items = values();
    const seen = new Set(items.map((item) => normalized(item)));
    parts.forEach((part) => {
      if (!seen.has(normalized(part))) {
        items.push(part);
        seen.add(normalized(part));
      }
    });
    write(items);
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      add(input.value);
      input.value = "";
    } else if (event.key === "Backspace" && !input.value) {
      const items = values();
      if (items.length) {
        items.pop();
        write(items);
      }
    }
  });
  input.addEventListener("blur", () => {
    if (input.value.trim()) {
      add(input.value);
      input.value = "";
    }
  });
  input.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text") ?? "";
    if (/[,;\n]/.test(text)) {
      event.preventDefault();
      add(text);
    }
  });
  box.addEventListener("click", (event) => {
    if (event.target === box || event.target === list) input.focus();
  });
  tagInputs.set(textarea.id, { render, add });
  render();
}

function refreshTagInputs() {
  tagInputs.forEach((tag) => tag.render());
}

const MAX_SEARCH_TERMS = 20;
let textSearchSources = 0;

function updateSearchTermsCount() {
  const count = linesFrom(elements.searchTerms).length;
  elements.searchTermsCount.textContent = `${count}/${MAX_SEARCH_TERMS}`;
  elements.searchTermsCount.classList.toggle("counter-over", count > MAX_SEARCH_TERMS);
  elements.termsEstimate.textContent = textSearchSources
    ? `≈ ${count * textSearchSources} consultas por busca completa (${textSearchSources} portais pesquisam por texto). Mais termos = mais vagas, mas a busca demora mais.`
    : "";
}

// --- gerador de termos da área ----------------------------------------------------
let termsState = { groups: [], recommended: [], limit: MAX_SEARCH_TERMS };
const selectedTerms = new Set();

function stacksForTerms() {
  if (selectedStacks.size) return [...selectedStacks];
  // nenhuma stack marcada: deduz pelas tecnologias principais já preenchidas
  const techs = new Set(linesFrom(elements.technologies).map(normalized));
  return (presetsState?.stacks ?? [])
    .filter((stack) => techs.has(normalized(stack.technologies[0])))
    .map((stack) => stack.id);
}

function renderTermsBuilder() {
  const recommended = new Set(termsState.recommended);
  elements.termsGroups.replaceChildren(
    ...termsState.groups.map((group) => {
      const box = document.createElement("div");
      box.className = "terms-group";
      box.appendChild(textElement("h4", "", group.label));
      const row = document.createElement("div");
      row.className = "chip-row";
      group.terms.forEach(({ term }) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip chip-small";
        chip.dataset.term = term;
        const on = selectedTerms.has(term);
        chip.setAttribute("aria-pressed", String(on));
        chip.classList.toggle("chip-on", on);
        chip.textContent = recommended.has(term) ? `★ ${term}` : term;
        chip.title = recommended.has(term) ? "Recomendado" : "";
        chip.addEventListener("click", () => {
          if (selectedTerms.has(term)) selectedTerms.delete(term);
          else selectedTerms.add(term);
          renderTermsBuilder();
        });
        row.appendChild(chip);
      });
      box.appendChild(row);
      return box;
    })
  );
  const count = selectedTerms.size;
  elements.termsSelectedCount.textContent = `${count} selecionados (cabem ${termsState.limit})`;
  elements.termsSelectedCount.classList.toggle("counter-over", count > termsState.limit);
}

async function loadTermsBuilder() {
  await loadPresets();
  const stacks = stacksForTerms();
  if (!stacks.length) {
    termsState = { groups: [], recommended: [], limit: MAX_SEARCH_TERMS };
    selectedTerms.clear();
    renderTermsBuilder();
    elements.termsStatus.textContent =
      "Marque ao menos uma stack acima (ou tenha a tecnologia principal dela em Tecnologias).";
    return;
  }
  const query = new URLSearchParams({
    stacks: stacks.join(","),
    levels: checkedValues(SENIORITY_BOXES()).join(","),
  });
  try {
    const response = await fetch(`/api/presets/terms?${query}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    termsState = payload;
    selectedTerms.clear();
    payload.recommended.forEach((term) => selectedTerms.add(term));
    renderTermsBuilder();
    elements.termsStatus.textContent = "";
  } catch (error) {
    elements.termsStatus.textContent = `Não foi possível gerar os termos: ${error.message}`;
  }
}

async function showTermsBuilder(show) {
  elements.termsBuilder.hidden = !show;
  elements.termsBuilderToggle.setAttribute("aria-expanded", String(show));
  if (show) await loadTermsBuilder();
}

function chosenTerms() {
  // recomendados primeiro (já estão em ordem de prioridade), depois os demais
  const ordered = [
    ...termsState.recommended,
    ...termsState.groups.flatMap((group) => group.terms.map(({ term }) => term)),
  ];
  return [...new Set(ordered)].filter((term) => selectedTerms.has(term));
}

function applyTerms(mode) {
  const chosen = chosenTerms();
  if (!chosen.length) {
    elements.termsStatus.textContent = "Marque ao menos um termo.";
    return;
  }
  const before = mode === "add" ? linesFrom(elements.searchTerms) : [];
  if (mode === "add") mergeLines(elements.searchTerms, chosen, MAX_SEARCH_TERMS);
  else elements.searchTerms.value = chosen.slice(0, MAX_SEARCH_TERMS).join("\n");
  const total = linesFrom(elements.searchTerms).length;
  const added = total - before.length;
  const left = chosen.filter((term) => !linesFrom(elements.searchTerms).includes(term)).length;
  updateSearchTermsCount();
  elements.termsStatus.textContent =
    `${added} termo(s) aplicados${left ? `; ${left} ficaram de fora (limite de ${MAX_SEARCH_TERMS})` : ""}. Salve as configurações para valer na próxima busca.`;
}

function fillPreferencesForm(payload) {
  elements.searchTerms.value = (payload.search_terms ?? []).join("\n");
  elements.locationScopes.value = (payload.location_scopes ?? []).join("\n");
  elements.technologies.value = (payload.technologies ?? []).join("\n");
  elements.excludedTerms.value = (payload.excluded_terms ?? []).join("\n");
  elements.requiredKeywords.value = (payload.required_keywords ?? []).join("\n");
  elements.bonusKeywords.value = (payload.bonus_keywords ?? []).join("\n");
  elements.blockedKeywords.value = (payload.blocked_keywords ?? []).join("\n");
  elements.excludedCompanies.value = (payload.excluded_companies ?? []).join("\n");
  elements.favoriteCompanies.value = (payload.favorite_companies ?? []).join("\n");
  const contracts = payload.contract_types ?? [];
  elements.contractBoxes.forEach((box) => setChecked(box, contracts));
  elements.avoidEnglish.checked = Boolean(payload.avoid_advanced_english);
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
  refreshTagInputs();
  updateSearchTermsCount();
  elements.preferencesImpact.hidden = true;
}

const SENIORITY_BOXES = () => [
  elements.seniorityInternship,
  elements.seniorityJunior,
  elements.seniorityMid,
  elements.senioritySenior,
];

let presetsState = null;
const selectedStacks = new Set();

function stackChip(stack) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = stack.custom ? "chip chip-custom" : "chip";
  chip.dataset.stack = stack.id;
  const on = selectedStacks.has(stack.id);
  chip.setAttribute("aria-pressed", String(on));
  chip.classList.toggle("chip-on", on);
  chip.textContent = stack.label;
  chip.title = stack.technologies.join(", ");
  chip.addEventListener("click", () => {
    const active = !selectedStacks.has(stack.id);
    if (active) selectedStacks.add(stack.id);
    else selectedStacks.delete(stack.id);
    chip.setAttribute("aria-pressed", String(active));
    chip.classList.toggle("chip-on", active);
  });
  if (!stack.custom) return chip;
  const group = document.createElement("span");
  group.className = "chip-group";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "chip-delete";
  remove.setAttribute("aria-label", `Excluir a stack ${stack.label}`);
  remove.textContent = "×";
  remove.addEventListener("click", () => deleteCustomStack(stack));
  group.append(chip, remove);
  return group;
}

function renderStackChips() {
  elements.stackChips.replaceChildren(...(presetsState?.stacks ?? []).map(stackChip));
}

async function loadPresets(force = false) {
  if (presetsState && !force) return;
  try {
    const response = await fetch("/api/presets", { cache: "no-store" });
    presetsState = await response.json();
    renderStackChips();
  } catch (error) {
    elements.stackChips.textContent = `Não foi possível carregar as stacks: ${error.message}`;
  }
}

function showNewStack(show) {
  elements.newStackForm.hidden = !show;
  elements.newStackToggle.setAttribute("aria-expanded", String(show));
  elements.newStackStatus.textContent = "";
  if (show) elements.newStackLabel.focus();
}

async function saveCustomStack() {
  const label = elements.newStackLabel.value.trim();
  const technologies = elements.newStackTechs.value;
  if (!label || !technologies.trim()) {
    elements.newStackStatus.textContent = "Dê um nome e informe ao menos uma tecnologia.";
    return;
  }
  try {
    const payload = await profileRequest("/api/stacks", {
      label,
      technologies,
      queries: elements.newStackQueries.value,
    });
    presetsState = payload;
    if (payload.created) selectedStacks.add(payload.created);
    renderStackChips();
    [elements.newStackLabel, elements.newStackTechs, elements.newStackQueries].forEach((input) => {
      input.value = "";
    });
    showNewStack(false);
    elements.preferencesStatus.textContent =
      `Stack "${label}" criada e marcada. Clique em Preencher sugestões para usar.`;
  } catch (error) {
    elements.newStackStatus.textContent = `Não foi possível criar: ${error.message}`;
  }
}

async function deleteCustomStack(stack) {
  if (!window.confirm(`Excluir a stack "${stack.label}"?`)) return;
  try {
    presetsState = await profileRequest("/api/stacks/delete", { id: stack.id });
    selectedStacks.delete(stack.id);
    renderStackChips();
    elements.preferencesStatus.textContent = `Stack "${stack.label}" excluída.`;
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível excluir: ${error.message}`;
  }
}

function mergeLines(element, additions, limit) {
  const items = linesFrom(element);
  const seen = new Set(items.map((item) => normalized(item)));
  additions.forEach((item) => {
    if (!seen.has(normalized(item)) && items.length < limit) {
      items.push(item);
      seen.add(normalized(item));
    }
  });
  element.value = items.join("\n");
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
    if (elements.suggestMerge.checked) {
      mergeLines(elements.technologies, suggestion.technologies, 40);
      mergeLines(elements.searchTerms, suggestion.search_terms, MAX_SEARCH_TERMS);
    } else {
      elements.technologies.value = suggestion.technologies.join("\n");
      elements.searchTerms.value = suggestion.search_terms.join("\n");
    }
    refreshTagInputs();
    updateSearchTermsCount();
    elements.preferencesStatus.textContent =
      "Sugestões preenchidas. Ajuste se quiser e clique em Salvar configurações.";
  } catch (error) {
    elements.preferencesStatus.textContent = `Não foi possível sugerir: ${error.message}`;
  }
}

function insightChip(text, title, onClick) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "chip chip-small";
  chip.textContent = text;
  if (title) chip.title = title;
  chip.addEventListener("click", () => {
    onClick();
    chip.remove();
  });
  return chip;
}

async function loadInsights() {
  try {
    const response = await fetch("/api/preferences/insights", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const techs = payload.technologies ?? [];
    elements.techInsights.hidden = techs.length === 0;
    elements.techInsightsChips.replaceChildren(
      ...techs.slice(0, 16).map(({ term, count }) =>
        insightChip(`+ ${term} (${count})`, "", () => tagInputs.get("technologies")?.add(term))
      )
    );
    elements.companyInsights.replaceChildren(
      ...(payload.companies ?? []).slice(0, 6).map(({ name, count }) =>
        insightChip(
          `+ ${name} (${count})`,
          "Empresa com várias vagas compatíveis na sua lista",
          () => tagInputs.get("favorite-companies")?.add(name)
        )
      )
    );
  } catch {
    elements.techInsights.hidden = true;
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
    required_keywords: linesFrom(elements.requiredKeywords),
    bonus_keywords: linesFrom(elements.bonusKeywords),
    blocked_keywords: linesFrom(elements.blockedKeywords),
    excluded_companies: linesFrom(elements.excludedCompanies),
    favorite_companies: linesFrom(elements.favoriteCompanies),
    contract_types: checkedValues(elements.contractBoxes),
    avoid_advanced_english: elements.avoidEnglish.checked,
  };
}

function impactText(summary, prefix) {
  const parts = [
    `${summary.ready} mais compatíveis`,
    `${summary.conditional + summary.ambiguous} a revisar`,
    `${summary.exclude} fora do perfil`,
  ];
  if (summary.other_stack) parts.splice(2, 0, `${summary.other_stack} de outra stack`);
  if (summary.recovered) parts.push(`${summary.recovered} voltam das descartadas na coleta`);
  if (summary.by_preferences) parts.push(`${summary.by_preferences} cortadas pelos filtros finos`);
  if (summary.boosted) parts.push(`${summary.boosted} com diferencial ou empresa favorita`);
  const changed = summary.changed ? ` ${summary.changed} mudaram de faixa.` : "";
  return `${prefix} ${parts.join(" · ")} (de ${summary.total - summary.off_topic} vagas de TI).${changed}`;
}

async function previewPreferences() {
  elements.preferencesImpact.hidden = false;
  elements.preferencesImpact.textContent = "Calculando impacto…";
  try {
    const summary = await profileRequest("/api/preferences/preview", currentPreferencesPayload());
    elements.preferencesImpact.textContent = impactText(summary, "Com estas configurações:");
  } catch (error) {
    elements.preferencesImpact.textContent = `Não foi possível calcular: ${error.message}`;
  }
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
    await Promise.all([loadPresets(), loadProfiles(), loadInsights(), loadConfiguredSources()]);
    textSearchSources = configuredSources.filter((source) => source.text_search).length;
    updateSearchTermsCount();
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
    const reapply = elements.reapplySaved.checked;
    const response = await fetch(`/api/preferences${reapply ? "?reapply=1" : ""}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.error || `HTTP ${response.status}`);
    preferencesLoaded = true;
    linkedinLoaded = false;
    elements.preferencesStatus.textContent = "Configurações salvas. Clique em Buscar vagas agora quando quiser.";
    if (saved.reapplied) {
      elements.preferencesImpact.hidden = false;
      elements.preferencesImpact.textContent = impactText(saved.reapplied, "Reaplicado às vagas salvas:");
      await refreshState();
    } else if (saved.reapply_skipped) {
      elements.preferencesImpact.hidden = false;
      elements.preferencesImpact.textContent = saved.reapply_skipped;
    }
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
document.querySelectorAll("textarea.tag-source").forEach(setupTagInput);
elements.searchTerms.addEventListener("input", updateSearchTermsCount);
elements.previewPreferences.addEventListener("click", previewPreferences);
elements.termsBuilderToggle.addEventListener("click", () => showTermsBuilder(elements.termsBuilder.hidden));
elements.termsRecommended.addEventListener("click", () => {
  selectedTerms.clear();
  termsState.recommended.forEach((term) => selectedTerms.add(term));
  renderTermsBuilder();
});
elements.termsClear.addEventListener("click", () => {
  selectedTerms.clear();
  renderTermsBuilder();
});
elements.termsAdd.addEventListener("click", () => applyTerms("add"));
elements.termsReplace.addEventListener("click", () => applyTerms("replace"));
// stacks ou níveis mudaram com o gerador aberto: recalcula
elements.stackChips.addEventListener("click", () => {
  if (!elements.termsBuilder.hidden) window.setTimeout(loadTermsBuilder, 0);
});
SENIORITY_BOXES().forEach((box) =>
  box.addEventListener("change", () => {
    if (!elements.termsBuilder.hidden) loadTermsBuilder();
  })
);
elements.newStackToggle.addEventListener("click", () => showNewStack(elements.newStackForm.hidden));
elements.newStackCancel.addEventListener("click", () => showNewStack(false));
elements.newStackSave.addEventListener("click", saveCustomStack);
[elements.newStackLabel, elements.newStackTechs, elements.newStackQueries].forEach((input) =>
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveCustomStack();
    }
  })
);
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
elements.pauseButton.addEventListener("click", () =>
  controlSearch(dashboardState.paused ? "resume" : "pause")
);
elements.stopButton.addEventListener("click", () => controlSearch("stop"));
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
elements.autoExportEnabled.addEventListener("change", saveAutoExport);
elements.autoExportSave.addEventListener("click", saveAutoExport);
elements.autoExportRun.addEventListener("click", runAutoExport);
elements.autoExportOpen.addEventListener("click", openAutoExportFolder);
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
elements.quickChips.forEach((chip) => chip.addEventListener("click", () => {
  const name = chip.dataset.quick;
  if (quickFilters.has(name)) quickFilters.delete(name);
  else quickFilters.add(name);
  syncQuickChips();
  saveFilters();
  visibleRows = ROW_PAGE_SIZE;
  renderTable();
}));
elements.newsShow.addEventListener("click", showNews);
elements.newsDismiss.addEventListener("click", () => {
  markSeen((dashboardState.jobs ?? []).map((job) => job.canonical_url));
  renderNews();
  renderTable();
});
elements.toastUndo.addEventListener("click", () => {
  const undo = toastUndo;
  elements.toast.hidden = true;
  toastUndo = null;
  if (undo) undo();
});
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

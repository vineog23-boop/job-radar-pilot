"use strict";

const elements = {
  searchButton: document.querySelector("#search-button"),
  liveStatus: document.querySelector("#live-status"),
  textFilter: document.querySelector("#text-filter"),
  sourceFilter: document.querySelector("#source-filter"),
  matchFilter: document.querySelector("#match-filter"),
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
};

let dashboardState = { jobs: [], report: {}, status: "IDLE", sources: {} };
let refreshTimer;

function normalized(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function hasMismatch(job) {
  return (job.match_labels ?? []).some((label) =>
    String(label).startsWith("SENIORITY_MISMATCH")
  );
}

function filteredJobs() {
  const text = normalized(elements.textFilter.value.trim());
  const source = elements.sourceFilter.value;
  const match = elements.matchFilter.value;

  return (dashboardState.jobs ?? []).filter((job) => {
    const haystack = normalized([
      job.title,
      job.company,
      job.location,
      ...(job.technologies ?? []),
      ...(job.match_labels ?? []),
    ].join(" "));
    if (text && !haystack.includes(text)) return false;
    if (source && job.source !== source) return false;
    if (match === "compatible" && hasMismatch(job)) return false;
    if (match === "mismatch" && !hasMismatch(job)) return false;
    return true;
  });
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
    const titleCell = document.createElement("td");
    titleCell.append(
      textElement("div", "job-title", job.title || "Cargo não informado"),
      textElement(
        "span",
        "job-meta",
        (job.technologies ?? []).slice(0, 4).join(" · ") || "Tecnologias não informadas"
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
        `match-pill ${hasMismatch(job) ? "warn" : "good"}`,
        hasMismatch(job) ? "Com ressalva" : "Mais compatível"
      )
    );
    row.appendChild(matchCell);

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
  elements.summaryMatches.textContent = String(jobs.filter((job) => !hasMismatch(job)).length);

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

function renderSources() {
  const liveSources = Object.values(dashboardState.sources ?? {});
  const sources = liveSources.length ? liveSources : (dashboardState.report?.sources ?? []);
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

elements.searchButton.addEventListener("click", startSearch);
[elements.textFilter, elements.sourceFilter, elements.matchFilter].forEach((filter) => {
  filter.addEventListener("input", renderTable);
  filter.addEventListener("change", renderTable);
});
elements.toggleSources.addEventListener("click", () => {
  const willShow = elements.sourceStatuses.hidden;
  elements.sourceStatuses.hidden = !willShow;
  elements.toggleSources.textContent = willShow ? "Ocultar detalhes" : "Ver detalhes";
});

refreshState();

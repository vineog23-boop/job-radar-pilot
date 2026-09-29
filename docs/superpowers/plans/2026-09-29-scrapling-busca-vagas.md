# Scrapling Job Search Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instalar o Scrapling v0.4.15 em ambiente Python 3.13 isolado e entregar um coletor independente que pesquisa os portais configurados e produz JSONL validável por outra IA, CSV e relatório de cobertura.

**Architecture:** O clone upstream fica imutável em `vendor/Scrapling`, enquanto o consumidor vive em `job-radar-pilot` como pacote Python separado. Adaptadores por tipo de fonte convertem páginas em um modelo comum; um pipeline aplica normalização, classificação, deduplicação e escrita atômica sem acessar o fluxo existente de vagas.

**Tech Stack:** Python 3.13, Scrapling 0.4.15 com extra `fetchers`, PyYAML, jsonschema, pytest e PowerShell.

**Spec:** `docs/superpowers/specs/2026-09-29-scrapling-busca-vagas-design.md`

## Global Constraints

- Fixar o clone oficial `https://github.com/D4Vinci/Scrapling.git` na tag `v0.4.15` e registrar o commit resolvido.
- Usar `C:\Users\vine\AppData\Local\Programs\Python\Python313\python.exe` e `job-radar-pilot\.venv`; nenhuma instalação global.
- Não acessar nem alterar SQLite, Notion, RADAR, `pipeline-state.json` ou qualquer arquivo de `C:\Users\vine\Documents\Vagas Dev`.
- Não automatizar LinkedIn autenticado, candidatura, CAPTCHA, 2FA ou bypass de controle de acesso.
- Não persistir senha, token, cookie, perfil de navegador ou HTML integral em Git ou `output`.
- Respeitar `robots.txt`, limites configurados e termos aplicáveis; bloqueio encerra somente a fonte afetada.
- Produzir UTF-8 em `output/vagas.jsonl`, `output/vagas.csv` e `output/relatorio-execucao.json` por troca atômica de arquivo.
- Toda dependência nova e o download dos navegadores exigem confirmação explícita do usuário antes da execução da Task 1.

## Review Focus

- Configuração com fonte, URL ou seletor inválido deve falhar antes de fazer requisição; coberto na Task 2.
- URL repetida, parâmetros de rastreamento e paginação cíclica não podem duplicar vaga nem criar loop; coberto nas Tasks 3 e 6.
- Página de login, CAPTCHA, 2FA, rate limit ou alerta de atividade deve gerar `BLOCKED` sanitizado e parar só aquela fonte; coberto na Task 4.
- Texto em português com acentos, datas ausentes e campos parciais devem continuar válidos no schema; coberto nas Tasks 3 e 7.
- Falha durante escrita não pode substituir uma saída anterior válida por arquivo parcial; coberto na Task 7.

---

## Estrutura de arquivos

- `.gitignore`: exclui clone upstream, venv, perfis de navegador, caches e saídas geradas.
- `scripts/setup.ps1`: clona/verifica a tag, cria a venv, instala dependências e navegadores.
- `scripts/run-job-radar.ps1`: executa o CLI sempre pelo Python isolado.
- `job-radar-pilot/pyproject.toml`: metadados, entry point e configuração do pytest.
- `job-radar-pilot/requirements.in`: dependências diretas declaradas.
- `job-radar-pilot/requirements.lock.txt`: ambiente resolvido depois da instalação.
- `job-radar-pilot/config/profile.yaml`: termos, níveis e localidades do usuário.
- `job-radar-pilot/config/sources.yaml`: registro completo das fontes e limites.
- `job-radar-pilot/schemas/vagas.schema.json`: contrato de cada linha JSONL.
- `job-radar-pilot/src/job_radar/models.py`: tipos comuns e enums.
- `job-radar-pilot/src/job_radar/config.py`: leitura e validação das configurações.
- `job-radar-pilot/src/job_radar/identity.py`: canonicalização e deduplicação.
- `job-radar-pilot/src/job_radar/classifier.py`: rótulos determinísticos de aderência.
- `job-radar-pilot/src/job_radar/fetching.py`: políticas de fetch, robots, retry e bloqueios.
- `job-radar-pilot/src/job_radar/sources/base.py`: contrato dos adaptadores.
- `job-radar-pilot/src/job_radar/sources/generic.py`: listas HTML configuráveis.
- `job-radar-pilot/src/job_radar/sources/gupy.py`: rotas públicas Gupy.
- `job-radar-pilot/src/job_radar/sources/indeed.py`: resultados públicos Indeed.
- `job-radar-pilot/src/job_radar/sources/dynamic.py`: portais JavaScript e handoff autenticado.
- `job-radar-pilot/src/job_radar/pipeline.py`: orquestra uma execução e isola fontes.
- `job-radar-pilot/src/job_radar/output.py`: schema, JSONL, CSV e relatório atômicos.
- `job-radar-pilot/src/job_radar/cli.py`: interface `job-radar collect` e `validate-output`.
- `job-radar-pilot/tests/fixtures/`: HTML mínimo sanitizado por família de portal.
- `job-radar-pilot/tests/`: testes unitários e de integração offline.
- `job-radar-pilot/README.md`: instalação, execução, limites e formato para outra IA.

### Task 1: Ambiente reproduzível e clone upstream

**Files:**
- Create: `.gitignore`
- Create: `scripts/setup.ps1`
- Create: `job-radar-pilot/pyproject.toml`
- Create: `job-radar-pilot/requirements.in`
- Create after resolution: `job-radar-pilot/requirements.lock.txt`
- Test: `job-radar-pilot/tests/test_environment.py`

**Interfaces:**
- Consumes: Python 3.13 e Git disponíveis no Windows.
- Produces: `.venv\Scripts\python.exe`, clone `vendor/Scrapling` em `v0.4.15` e pacote `scrapling` importável.

- [ ] **Step 1: Escrever o teste de contrato do ambiente**

Criar `test_environment.py` com `test_python_and_scrapling_versions()` afirmando Python `3.13.*`, `importlib.metadata.version("scrapling") == "0.4.15"`, `git -C vendor/Scrapling describe --tags --exact-match == "v0.4.15"` e um SHA de 40 caracteres retornado por `git rev-parse HEAD`.

- [ ] **Step 2: Executar o teste e confirmar RED**

Run: `C:\Users\vine\AppData\Local\Programs\Python\Python313\python.exe -m pytest job-radar-pilot/tests/test_environment.py -v`

Expected: FAIL porque ambiente/pacote ainda não existem.

- [ ] **Step 3: Criar os arquivos de instalação**

`setup.ps1` deve: resolver caminhos pelo próprio script; clonar apenas de `D4Vinci/Scrapling`; fazer checkout de `v0.4.15`; conferir que `git describe --tags --exact-match` retorna `v0.4.15`; criar `.venv` com Python 3.13; instalar `vendor/Scrapling[fetchers]`, PyYAML, jsonschema e pytest; instalar `job-radar-pilot` em modo editável; executar o instalador de navegadores pelo binário da venv; gerar `requirements.lock.txt`; nunca usar `--force` por padrão.

- [ ] **Step 4: Executar instalação após confirmação explícita do usuário**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`

Expected: clone na tag correta, instalação sem pacote global e saída contendo o commit upstream.

- [ ] **Step 5: Executar o teste e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_environment.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore scripts/setup.ps1 job-radar-pilot/pyproject.toml job-radar-pilot/requirements.in job-radar-pilot/requirements.lock.txt job-radar-pilot/tests/test_environment.py
git commit -m "build: instala Scrapling em ambiente isolado"
```

### Task 2: Modelos e configuração validada

**Files:**
- Create: `job-radar-pilot/src/job_radar/__init__.py`
- Create: `job-radar-pilot/src/job_radar/models.py`
- Create: `job-radar-pilot/src/job_radar/config.py`
- Create: `job-radar-pilot/config/profile.yaml`
- Create: `job-radar-pilot/config/sources.yaml`
- Test: `job-radar-pilot/tests/test_config.py`

**Interfaces:**
- Consumes: YAML local sem segredos.
- Produces: `load_profile(path: Path) -> SearchProfile`, `load_sources(path: Path) -> tuple[SourceConfig, ...]`, `VacancyRecord` e `SourceRunResult`.

- [ ] **Step 1: Escrever testes RED da configuração**

Testar `test_loads_complete_profile_and_sources()`, `test_rejects_unknown_source_kind()`, `test_rejects_non_https_start_url()` e `test_rejects_missing_selectors_before_network()`. A lista deve conter códigos únicos para Gupy, Indeed, EstágioTrainee, Eureca, Programathor, Casa do Dev, CIEE, Nube, Vagas.com, 99jobs, Cia de Talentos, Companhia de Estágios, O Trainee, Vida de Trainee, Seja Trainee e InfoJobs.

- [ ] **Step 2: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_config.py -v`

Expected: FAIL por módulos ausentes.

- [ ] **Step 3: Implementar modelos e loaders**

Definir enums `SourceKind`, `CollectionStatus` e `WorkplaceModel`; dataclasses imutáveis `SearchProfile`, `SourceConfig`, `VacancyRecord`, `SourceRunResult` e `RunReport`. Os loaders devem rejeitar chaves desconhecidas, códigos duplicados, URLs não HTTPS, limites fora de `1..100` e fonte genérica sem seletores obrigatórios.

- [ ] **Step 4: Preencher perfil e registro de fontes**

Configurar termos Java/backend/Spring/API/JPA/SQL/Maven/Docker/testes, níveis estágio/júnior e escopos remoto Brasil, São Carlos e região de Florianópolis. Cada fonte recebe `enabled`, `kind`, URL oficial, limite, intervalo mínimo e `requires_auth`; LinkedIn não entra no registro.

- [ ] **Step 5: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add job-radar-pilot/src/job_radar job-radar-pilot/config job-radar-pilot/tests/test_config.py
git commit -m "feat: define perfil e registro validado de fontes"
```

### Task 3: Normalização, identidade e classificação

**Files:**
- Create: `job-radar-pilot/src/job_radar/identity.py`
- Create: `job-radar-pilot/src/job_radar/classifier.py`
- Test: `job-radar-pilot/tests/test_identity.py`
- Test: `job-radar-pilot/tests/test_classifier.py`

**Interfaces:**
- Consumes: `VacancyRecord` e `SearchProfile` da Task 2.
- Produces: `canonicalize_url(url: str) -> str`, `identity_key(record: VacancyRecord) -> tuple[str, str]`, `deduplicate(records: Iterable[VacancyRecord]) -> DeduplicationResult` e `classify(record: VacancyRecord, profile: SearchProfile) -> VacancyRecord`.

- [ ] **Step 1: Escrever testes RED de identidade**

Cobrir remoção de `utm_*`, tokens e fragmentos; preservação de job ID; prioridade `source_job_id > canonical_url > fallback_hash`; duas URLs equivalentes; conflito de IDs; e fallback marcado como identidade fraca.

- [ ] **Step 2: Escrever testes RED de classificação**

Cobrir texto UTF-8 com acentos, aderência Java/Spring, estágio/júnior, sênior incompatível, remoto sem país como incerto, localização ausente e datas `null`. As asserções devem verificar apenas rótulos determinísticos, sem score inventado.

- [ ] **Step 3: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_identity.py job-radar-pilot/tests/test_classifier.py -v`

Expected: FAIL por funções ausentes.

- [ ] **Step 4: Implementar identidade e classificação**

Canonicalizar somente parâmetros conhecidos de rastreamento/sessão; nunca remover o identificador da vaga. Manter conflitos em `DeduplicationResult.ambiguous`. Classificar por termos normalizados com Unicode casefold e preservar a evidência que originou cada rótulo.

- [ ] **Step 5: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_identity.py job-radar-pilot/tests/test_classifier.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add job-radar-pilot/src/job_radar/identity.py job-radar-pilot/src/job_radar/classifier.py job-radar-pilot/tests/test_identity.py job-radar-pilot/tests/test_classifier.py
git commit -m "feat: normaliza e classifica vagas coletadas"
```

### Task 4: Fetch seguro e detecção de bloqueios

**Files:**
- Create: `job-radar-pilot/src/job_radar/fetching.py`
- Test: `job-radar-pilot/tests/test_fetching.py`

**Interfaces:**
- Consumes: `SourceConfig` da Task 2 e classes `FetcherSession`/`StealthySession` do Scrapling.
- Produces: `FetchPolicy.fetch(url: str, source: SourceConfig) -> FetchResult` e `detect_block(response: ResponseLike) -> BlockReason | None`.

- [ ] **Step 1: Escrever testes RED com doubles locais**

Cobrir robots negando rota, timeout com até duas tentativas e backoff, HTTP 429 sem retry agressivo, login, CAPTCHA, 2FA e alerta de atividade. Afirmar que mensagens e metadados não contêm query sensível, cookie ou corpo HTML.

- [ ] **Step 2: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_fetching.py -v`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar `FetchPolicy`**

Usar fetch HTTP por padrão e navegador apenas para `SourceKind.DYNAMIC`; consultar robots antes do fetch; impor timeout, intervalo e máximo de duas tentativas; retornar estados tipados sem lançar detalhes sensíveis para o pipeline.

- [ ] **Step 4: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_fetching.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add job-radar-pilot/src/job_radar/fetching.py job-radar-pilot/tests/test_fetching.py
git commit -m "feat: adiciona coleta segura e bloqueios tipados"
```

### Task 5: Adaptadores das fontes

**Files:**
- Create: `job-radar-pilot/src/job_radar/sources/__init__.py`
- Create: `job-radar-pilot/src/job_radar/sources/base.py`
- Create: `job-radar-pilot/src/job_radar/sources/generic.py`
- Create: `job-radar-pilot/src/job_radar/sources/gupy.py`
- Create: `job-radar-pilot/src/job_radar/sources/indeed.py`
- Create: `job-radar-pilot/src/job_radar/sources/dynamic.py`
- Create: `job-radar-pilot/tests/fixtures/*.html`
- Test: `job-radar-pilot/tests/test_sources.py`

**Interfaces:**
- Consumes: `FetchResult`, `SourceConfig` e `VacancyRecord`.
- Produces: protocolo `SourceAdapter.collect(config: SourceConfig, fetcher: FetchPolicy) -> SourceRunResult` e `adapter_for(config: SourceConfig) -> SourceAdapter`.

- [ ] **Step 1: Capturar fixtures mínimos e sanitizados**

Guardar somente trechos necessários de páginas públicas para as famílias genérica, Gupy, Indeed e dinâmica. Remover scripts, tokens, cookies, dados pessoais e conteúdo não relacionado.

- [ ] **Step 2: Escrever testes RED dos adaptadores**

Para cada família, afirmar extração de ID/URL/título/empresa/localidade; página parcial com campos `null`; link de detalhe relativo; paginação seguinte; login detectado; seletor ausente como erro de layout. Incluir teste de fábrica para todos os códigos configurados.

- [ ] **Step 3: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_sources.py -v`

Expected: FAIL por adaptadores ausentes.

- [ ] **Step 4: Implementar contrato e adaptador genérico**

`GenericListAdapter` usa seletores do YAML e resolve URLs contra a origem. Não deve inferir empresa, nível ou modalidade quando a página não os declarar.

- [ ] **Step 5: Implementar adaptadores Gupy e Indeed**

Usar apenas rotas públicas observáveis, extrair identidade forte da rota/parâmetro oficial e nunca persistir parâmetros de sessão. Redirecionamento para ATS oficial deve preservar ambas as origens no resultado, com a URL final como canônica quando inequívoca.

- [ ] **Step 6: Implementar adaptador dinâmico e handoff**

Usar navegador para Eureca, 99jobs, Cia de Talentos e fontes configuradas como dinâmicas; ausência de sessão retorna `AUTH_REQUIRED` com URL exata, nunca tentativa de login automatizado.

- [ ] **Step 7: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_sources.py -v`

Expected: PASS para todas as famílias e códigos de fonte.

- [ ] **Step 8: Commit**

```powershell
git add job-radar-pilot/src/job_radar/sources job-radar-pilot/tests/fixtures job-radar-pilot/tests/test_sources.py
git commit -m "feat: adiciona adaptadores dos portais de vagas"
```

### Task 6: Pipeline isolado e limites de paginação

**Files:**
- Create: `job-radar-pilot/src/job_radar/pipeline.py`
- Test: `job-radar-pilot/tests/test_pipeline.py`

**Interfaces:**
- Consumes: loaders, adaptadores, classificador e deduplicador das Tasks 2–5.
- Produces: `JobRadarPipeline.run(source_codes: Sequence[str] | None = None) -> PipelineResult`.

- [ ] **Step 1: Escrever testes RED do pipeline**

Cobrir uma fonte bem-sucedida e outra bloqueada no mesmo run, fonte vazia, filtro por códigos, limite de páginas, URL de próxima página repetida, duplicata entre fontes e relatório com contagens reconciliadas.

- [ ] **Step 2: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_pipeline.py -v`

Expected: FAIL por pipeline ausente.

- [ ] **Step 3: Implementar `JobRadarPipeline`**

Executar fontes sequencialmente no primeiro piloto para manter limites previsíveis; isolar exceções por fonte; rastrear URLs visitadas; interromper em limite, loop, bloqueio ou paginação esgotada; só então classificar e deduplicar.

- [ ] **Step 4: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add job-radar-pilot/src/job_radar/pipeline.py job-radar-pilot/tests/test_pipeline.py
git commit -m "feat: orquestra coleta isolada por fonte"
```

### Task 7: Saídas validadas e escrita atômica

**Files:**
- Create: `job-radar-pilot/schemas/vagas.schema.json`
- Create: `job-radar-pilot/src/job_radar/output.py`
- Test: `job-radar-pilot/tests/test_output.py`

**Interfaces:**
- Consumes: `PipelineResult` da Task 6.
- Produces: `write_outputs(result: PipelineResult, output_dir: Path) -> OutputManifest` e `validate_jsonl(path: Path, schema_path: Path) -> ValidationResult`.

- [ ] **Step 1: Escrever testes RED do contrato de saída**

Validar uma linha completa e outra parcial com acentos/datas nulas; rejeitar campo obrigatório ausente e propriedade desconhecida; conferir cabeçalho CSV; reconciliar relatório; simular falha antes de `os.replace` e provar que arquivos válidos anteriores permanecem intactos.

- [ ] **Step 2: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_output.py -v`

Expected: FAIL por schema/writer ausentes.

- [ ] **Step 3: Criar JSON Schema**

Usar Draft 2020-12, `additionalProperties: false`, timestamps ISO 8601, URLs HTTPS e os campos definidos na especificação. Campos factualmente ausentes aceitam `null`; listas permanecem arrays.

- [ ] **Step 4: Implementar writers e validador**

Escrever temporários UTF-8 no diretório de destino, validar cada JSONL antes da troca e usar `os.replace`. O relatório inclui versão `0.4.15`, commit upstream, fontes, contagens, paginação e erros sanitizados.

- [ ] **Step 5: Executar testes e confirmar GREEN**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_output.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add job-radar-pilot/schemas/vagas.schema.json job-radar-pilot/src/job_radar/output.py job-radar-pilot/tests/test_output.py
git commit -m "feat: gera saidas estruturadas e atomicas"
```

### Task 8: CLI, documentação e verificação ponta a ponta

**Files:**
- Create: `job-radar-pilot/src/job_radar/cli.py`
- Create: `scripts/run-job-radar.ps1`
- Create: `job-radar-pilot/README.md`
- Test: `job-radar-pilot/tests/test_cli.py`
- Modify: `job-radar-pilot/pyproject.toml`

**Interfaces:**
- Consumes: `JobRadarPipeline`, `write_outputs` e `validate_jsonl`.
- Produces: `job-radar collect [--source CODE] [--output PATH] [--dry-run]` e `job-radar validate-output PATH`.

- [ ] **Step 1: Escrever testes RED do CLI**

Cobrir ajuda, `--dry-run` sem rede, seleção repetível de fontes, código desconhecido com exit code 2, execução parcial com exit code 3 e validação de JSONL com exit code 0/1.

- [ ] **Step 2: Executar testes e confirmar RED**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests/test_cli.py -v`

Expected: FAIL por entry point ausente.

- [ ] **Step 3: Implementar CLI e wrapper PowerShell**

Usar `argparse`; `run-job-radar.ps1` resolve a venv pelo workspace e recusa Python global. `--dry-run` carrega/valida configurações e lista o plano sem efetuar fetch.

- [ ] **Step 4: Documentar operação e consumo por IA**

O README deve explicar setup, dry run, coleta, validação, campos JSONL, códigos de saída, fontes bloqueadas, autenticação manual e a garantia de independência de `Vagas Dev`. Incluir prompt curto de exemplo para outra IA filtrar `vagas.jsonl` sem tratar rótulo como fato.

- [ ] **Step 5: Executar suíte completa**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests -v`

Expected: todos os testes PASS.

- [ ] **Step 6: Executar dry run**

Run: `.\scripts\run-job-radar.ps1 --dry-run`

Expected: todas as fontes habilitadas listadas, configuração válida e zero requisições.

- [ ] **Step 7: Executar smoke test público limitado**

Run: `.\scripts\run-job-radar.ps1 --source programathor --output .\job-radar-pilot\output`

Expected: um run terminal honesto (`SUCCESS`, `EMPTY`, `PARTIAL` ou `BLOCKED`), JSONL válido quando houver vagas e relatório sempre presente; nunca declarar cobertura além das páginas percorridas.

- [ ] **Step 8: Validar saída e ausência de segredos**

Run: `.\scripts\run-job-radar.ps1 validate-output .\job-radar-pilot\output\vagas.jsonl`

Expected: exit code 0. Em seguida, pesquisar nas saídas por padrões `cookie`, `authorization`, `token`, `password`, HTML integral e caminhos de `Vagas Dev`; esperado zero achados sensíveis.

- [ ] **Step 9: Commit**

```powershell
git add job-radar-pilot/src/job_radar/cli.py job-radar-pilot/pyproject.toml job-radar-pilot/tests/test_cli.py job-radar-pilot/README.md scripts/run-job-radar.ps1
git commit -m "feat: entrega piloto executavel de busca de vagas"
```

### Task 9: Revisão final e evidência de entrega

**Files:**
- Modify only if review finds defects: files from Tasks 1–8

**Interfaces:**
- Consumes: projeto completo e resultados dos testes.
- Produces: evidência final reproduzível e árvore Git limpa fora dos anexos preexistentes.

- [ ] **Step 1: Conferir aderência à especificação**

Comparar cada seção da spec com arquivos, testes e documentação; registrar qualquer limitação real de fonte no README, sem prometer cobertura não testada.

- [ ] **Step 2: Reexecutar verificações finais**

Run: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests -v`

Run: `.\scripts\run-job-radar.ps1 --dry-run`

Run: `git status --short`

Expected: testes verdes, dry run válido e somente anexos preexistentes não rastreados.

- [ ] **Step 3: Commit de correções, se necessário**

```powershell
git add <somente-arquivos-corrigidos>
git commit -m "fix: conclui validacao do piloto Scrapling"
```

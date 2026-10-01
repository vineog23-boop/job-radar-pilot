# CLAUDE.md — Job Radar Pilot

Contexto para o Claude Code (local ou na nuvem). Leia antes de mexer em qualquer coisa.
Responda e escreva commits em **português do Brasil**.

## O que é

Coletor local de vagas de TI para o Vinicius (estudante de ADS, foco em Java backend).
Consulta ~25 portais públicos com o Scrapling, classifica cada vaga contra o perfil dele
(stacks, nível, local, modelo de trabalho, palavras-chave), grava `vagas.jsonl`/CSV/relatório e
mostra tudo num painel web local (`http://127.0.0.1:8765`). Roda no **Windows** do usuário,
aberto por um atalho ("Radar de Vagas").

## Mapa do repositório

```
/                         raiz do git (github.com/vineog23-boop/job-radar-pilot)
├── CLAUDE.md             este arquivo
├── docs/MELHORIAS-PENDENTES.md   backlog priorizado → comece por aqui
├── abrir-interface.ps1, buscar-vagas.ps1, scripts/*.ps1   launchers do Windows
├── vendor/Scrapling      clone fixado do Scrapling v0.4.15 (NÃO versionado, NÃO editar)
└── job-radar-pilot/
    ├── config/sources.yaml   portais (kind, seletores, paginação, tech_focus, api…)
    ├── config/profile.yaml   perfil padrão (preferências pessoais — não alterar sem pedir)
    ├── schemas/vagas.schema.json   contrato do JSONL (toda saída é validada contra ele)
    ├── src/job_radar/        código (ver abaixo)
    ├── tests/                ~45 arquivos, ~775 testes (pytest + Playwright)
    └── README.md             manual do usuário (manter atualizado a cada feature)
```

### Fluxo (`src/job_radar/`)

`cli.py collect` → `config.py` (lê YAML) → `preferences.py` (perfil do painel sobre o
`profile.yaml`) → `pipeline.py` (por portal: termos de busca → `sources/*` adaptadores via
`fetching.FetchPolicy`) → `classifier.py` (rótulos `FIT:*`, `FIT_SCORE`, `*_MATCH/MISMATCH`) →
`enrich.py` (página de detalhe) → `identity.py` (dedupe entre portais, `ALSO_SEEN_IN`) →
`history.py` (`STATUS:NEW`) → `output.py` (JSONL/CSV/relatório; `cleanup.prune_payloads`
descarta inúteis e guarda em `vagas-descartadas-na-coleta.jsonl`) → `webapp.py` (servidor +
API) + `web/` (HTML/CSS/JS sem framework).

Módulos de apoio: `presets.py` (25 stacks, stacks personalizadas, catálogo/gerador de termos),
`reclassify.py` (reaplica o perfil às vagas salvas sem nova coleta), `run_control.py`
(pausar/parar via arquivo `output/.radar-control`), `cleanup.py` (regras, backup e desfazer),
`profiles.py` (perfis nomeados), `tracking.py` (salva/aplicada/descartada), `fit.py` (leitura
única da faixa `FIT:`, nomes, motivos e `job_technologies`), `evaluation.py` (`job-radar avaliar`:
mede o classificador na amostra real), `output_lock.py` (trava da pasta de saída entre coleta e
painel), `xlsx_export.py`
(planilha feita à mão com zipfile/XML — não há openpyxl), `linkedin_import.py` (só importa
links/textos colados), `manual_search.py` (links oficiais de busca do LinkedIn), `adaptive.py`
(fallback adaptativo de cards), `geo.py`, `dates.py`, `text_cleaning.py`.

Adaptadores (`sources/`): `generic`, `gupy`, `indeed`, `dynamic` (navegador), `json_api`
(APIs JSON públicas, ex.: Gupy, Primeira Vaga Tech), `rss` (feeds, ex.: Empregos Tech).

Rótulos importantes (`match_labels`): `FIT:READY|CONDITIONAL|AMBIGUOUS|OTHER_STACK|EXCLUDE`,
`OTHER_STACK:<stack>`,
`FIT_SCORE:0-4|-1`, `RELEVANCE:OFF_TOPIC`, `TECH_MATCH:`, `SENIORITY_*`, `LOCATION_*`,
`WORKPLACE_*`, `KEYWORD_MATCH/MISSING/BLOCKED`, `BONUS_MATCH`, `COMPANY_EXCLUDED/FAVORITE`,
`CONTRACT:`/`CONTRACT_MISMATCH:`, `LANGUAGE:`/`LANGUAGE_MISMATCH:`, `TITLE_EXCLUDED:`,
`STATUS:NEW`, `ALSO_SEEN_IN:`, `IMPORT:MANUAL`, `ENRICHED:DETAIL`. Ao criar rótulo novo:
atualizar `reclassify._CLASSIFIER_PREFIXES` (se for do classificador), os motivos em
`fit.REASON_LABELS` e `web/app.js` (`REASON_LABELS`/`CRITERIA_LABELS`). Faixa `FIT:` nova:
`fit.FIT_STATES`/`FIT_NAMES`, `app.js` (`fitState`, `fitLabel`, filtro e ordem), `index.html`
(opção do filtro), `export_document` (seção) e `evaluation.CATEGORY_ORDER`.

Dados locais do usuário (fora do repo, Windows): `%LOCALAPPDATA%\JobRadar\` →
`search-preferences.json`, `profiles/`, `cleanup-rules.json`, `custom-stacks.json`,
`tracking.json`, `history.json`. Saída: `job-radar-pilot/output/` (ignorada pelo git).

## Ambiente na nuvem (setup)

`vendor/` não está no repositório. Python **3.13** é obrigatório (`requires-python >=3.13,<3.14`).

```bash
git clone --depth 1 --branch v0.4.15 https://github.com/D4Vinci/Scrapling vendor/Scrapling
python3.13 -m venv job-radar-pilot/.venv
job-radar-pilot/.venv/bin/pip install -e "vendor/Scrapling[fetchers]" -e "job-radar-pilot[test]"
job-radar-pilot/.venv/bin/python -m playwright install --with-deps chromium
PYTHONPATH=job-radar-pilot/src job-radar-pilot/.venv/bin/python -m pytest job-radar-pilot/tests -q -p no:cacheprovider
```

- `tests/test_environment.py` exige Python 3.13, Scrapling 0.4.15 e o clone com `.git` na tag
  `v0.4.15`. Se falhar só por ambiente, isso **não** é regressão — mas não "conserte" o teste.
- A suíte roda de qualquer pasta (raiz ou `job-radar-pilot/`): teste novo usa
  `Path(__file__)` para achar arquivos, nunca caminho relativo à pasta atual (isso deixou o CI
  vermelho de 30/09 a 01/10/2026).
- Na nuvem, se o Playwright do venv pedir outra revisão do Chromium que a pré-instalada em
  `/opt/pw-browsers`, aponte `PLAYWRIGHT_BROWSERS_PATH` para uma pasta com um link do
  `headless_shell` existente no nome esperado, em vez de baixar.
- O CI (`.github/workflows/tests.yml`) roda a suíte no Windows a cada push/PR: ele é o juiz final.
- No Windows do usuário: `.\job-radar-pilot\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`
  (rodar de dentro de `job-radar-pilot`).

### O que NÃO funciona na nuvem (e não é bug)

- `.ps1`, `.cmd`, `.lnk`, `%LOCALAPPDATA%`, notificação do Windows: são do PC do usuário. Não
  apague nem "corrija" para Linux; se mexer, mantenha compatível com PowerShell 7/Windows.
- **Coleta real nos portais**: a rede da nuvem é restrita e o IP é de datacenter. Não rode
  `job-radar collect` contra os portais na nuvem; valide com testes e fixtures.

## Regras do projeto (inegociáveis)

1. **Não editar `vendor/Scrapling`.** Comportamento novo vai em `src/job_radar`.
2. **LinkedIn: nada de raspagem, login automático, cookies ou conta falsa.** O fluxo seguro é
   links oficiais de busca + importação do que o usuário cola. Recusar mesmo se pedido.
3. Respeitar `robots.txt`, `min_interval_seconds` e a detecção de bloqueio do `FetchPolicy`.
   Nunca contornar CAPTCHA, login ou 2FA. Portal que bloqueia é desabilitado, não burlado.
4. Não versionar `output/`, perfis de navegador, cookies, tokens, HTML integral de páginas
   nem dados pessoais. Fixtures de teste: só o trecho necessário, sanitizado.
5. Não alterar `config/profile.yaml` (preferências pessoais) sem pedir.
6. Toda saída continua válida contra `schemas/vagas.schema.json`.
7. Limpeza é sempre não destrutiva por padrão: prévia antes, backup e "desfazer".

## Como trabalhar

- **Plano antes de código** em mudanças grandes; apresente e espere aprovação.
- **Teste primeiro** (vermelho → verde). Bug corrigido ganha teste de regressão.
- **Um commit por item**, em português: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Trabalhe numa **branch** e abra PR; nunca force-push no `main`.
- Mudou o classificador? Rode `job-radar avaliar --base tests/fixtures/avaliacao-base-antes-p1.json`
  (ou uma base salva com `--salvar` antes da mudança) e cole o antes × depois no PR.
- Ao terminar um item: suíte inteira verde, README atualizado se o usuário perceber a mudança,
  e marque o item em `docs/MELHORIAS-PENDENTES.md`.
- Refatoração = **sem mudança de comportamento**; os testes existentes devem passar intactos.

## Armadilhas conhecidas

- **Final de linha**: no repositório tudo é LF, exceto `.cmd`/`.bat` (CRLF via `.gitattributes`).
  No Windows o checkout pode converter para CRLF; preserve o que o arquivo já usa.
- **Painel em execução mantém código antigo**: no PC do usuário, depois de mexer em Python é
  preciso matar o processo `job_radar.webapp` e reabrir pelo atalho. Lembre disso no resumo.
- Testes do painel usam Playwright com seletores por **id** e por **nome acessível** de botões
  (ex.: "Configurar busca", "Limpeza", "Exportar vagas", "⏸ Pausar busca"). Renomear botão
  quebra teste — atualize os dois juntos.
- Campos de etiquetas do painel: o `<textarea>` original fica oculto e guarda o valor (uma
  etiqueta por linha); a digitação é no `#<id>-entry`.
- `PUT /api/preferences?reapply=1` reclassifica `vagas.jsonl` — rótulos que não são do
  classificador (`STATUS:`, `ALSO_SEEN_IN:`, `IMPORT:`…) precisam ser preservados.
- Limites: 20 termos de busca; 40 tecnologias; `MAX_API_REQUESTS=40` por fonte JSON.
- Coleta parada pelo usuário sai com código **4** e grava parcial (`merge_unrefreshed` +
  `partial_sources`) para não apagar vagas dos portais não consultados.
- Coleta e painel compartilham `output/.radar-output.lock` (`output_lock.OutputLock`). Coleta
  com a trava ocupada sai com **5** (`EXIT_BUSY`); ação do painel que regrava o `vagas.jsonl`
  (limpar, desfazer, reaplicar, importar) precisa segurar a trava e responder 409 se ocupada.
- `technologies` é **dado do portal**: o classificador não escreve nele. Para exibir, use
  `fit.job_technologies(job)` (Python) / `jobTechnologies(job)` (app.js), que juntam `TECH_MATCH:`.
- Servidor do painel: todo POST/PUT exige `application/json` e o `Host` precisa ser o próprio
  painel (CSRF/DNS rebinding). Teste novo de API manda o cabeçalho JSON até em POST sem corpo.
- Quem **regrava** o `vagas.jsonl` lê com `cleanup.read_jobs_for_rewrite` (recusa linha
  ilegível); `tracking.json` ilegível desliga a poda, nunca a proteção das vagas salvas.

## Perfil do usuário (para decisões de produto)

Estágio/júnior em Java + Spring Boot, remoto no Brasil ou região de São Carlos/SP e Grande
Florianópolis/SC. Mas o produto deve servir **qualquer stack e nível** (perfis no painel).
Ele prefere explicações didáticas e entende Java/Spring/SQL melhor que Python/JS.

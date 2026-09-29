# Job Radar Pilot — melhorias pendentes

Documento para orientar uma sessão do Claude Code (nuvem ou local). Baseado em coletas
reais de 29/09/2026 (2.990 vagas únicas, 21 fontes) e na revisão do código.

## Regras de trabalho (valem para todos os itens)

1. **Testes antes do código.** Escreva o teste que falha, veja falhar, implemente, veja passar.
2. **Um commit por item**, mensagem em português no formato `feat:`/`fix:`/`refactor:`.
3. **Não editar `vendor/Scrapling`.** Não commitar `output/`, perfis de navegador, cookies,
   tokens ou HTML integral de páginas.
4. **Respeitar `robots.txt`**, limites por fonte (`min_interval_seconds`) e nunca contornar
   login, CAPTCHA ou 2FA. LinkedIn continua fora da coleta automática.
5. Não alterar `config/profile.yaml` (preferências pessoais) sem pedir.
6. Suíte atual: 385 testes passam. Dois falham **só** onde não há `.git` no vendor
   (`test_environment`, `test_output::test_csv_header_and_report_counts_are_reconciled`); não
   são regressões.
7. Cada item tem "Pronto quando". Só marque como feito se os critérios forem atendidos.

## Ambiente na nuvem (leia antes de começar)

- O sandbox de nuvem tem rede restrita por padrão. **Testes unitários rodam sem rede.** Coletas
  reais nos portais podem ficar bloqueadas; não dependa delas. Use fixtures salvas.
- `vendor/Scrapling` **não** está no repositório (`.gitignore`). Setup necessário:
  `git clone --branch v0.4.15 https://github.com/D4Vinci/Scrapling vendor/Scrapling`, depois
  `python3.13 -m venv .venv`, `pip install -e "vendor/Scrapling[fetchers]" -e "job-radar-pilot[test]"`
  e `playwright install chromium` (com `--with-deps` no Linux).
- Python obrigatório: 3.13. Os scripts `.ps1` são para Windows; na nuvem rode
  `PYTHONPATH=job-radar-pilot/src python -m pytest job-radar-pilot/tests -q`.
- Testes do painel (`test_webapp`) usam Playwright/Chromium.

## Status após a sessão na nuvem (29/09/2026, branch `claude/elegant-hypatia-2rg9ix`)

Feito (com testes): 1.1, 1.2, 1.3, limpeza de título de 1.4, 2.1, 2.2 (conversão e
seletor opcional `published`), 2.4, 3.2, 3.3, 4.5 (CI), 4.6 (README). Extras pedidos pelo
usuário: stacks e termos de exclusão editáveis no painel; acompanhamento de vagas
(salva/aplicada/descartada) e exportação CSV filtrada.

Ainda aberto — **depende de acesso aos portais** (a rede da nuvem bloqueou todos):
1.4 (títulos descritivos de CIEE/Nube), seletores `published` e `company` reais (2.2/2.3),
3.1, 3.5, 3.6 e 4.4 (fixtures reais). Também abertos: 3.4 (notificação do Windows) e
4.1/4.2 (refatoração sem mudança de comportamento).

---

## P1 — Qualidade do filtro (`src/job_radar/classifier.py`) — maior impacto

Evidência: em 2.990 vagas, só 9 `READY` e 66 `CONDITIONAL`; 1.019 estágios foram excluídos só
por `LOCATION_MISMATCH:outside_scope`.

### 1.1 Vaga remota com cidade no campo local vira EXCLUDE (falso negativo)
- Teste real: título "Desenvolvedor Java Júnior", local "Curitiba, PR", resumo "Vaga 100% remota
  para todo o Brasil" → `FIT:EXCLUDE (LOCATION_MISMATCH:outside_scope)`.
- Esperado: se o texto (título/resumo/local) indica remoto no Brasil, tratar como
  `LOCATION_MATCH:remote_brazil` mesmo que o campo local traga a sede. Vaga presencial em outra
  cidade continua `EXCLUDE`.
- Pronto quando: casos com "100% remoto", "home office", "trabalho remoto", "remoto (Brasil)" e
  cidade fora do escopo saem `READY`/`CONDITIONAL`; "presencial - Lajeado/RS" continua `EXCLUDE`;
  "remoto EUA/Canadá" não vira `remote_brazil`.

### 1.2 Sinônimos de júnior/estágio não reconhecidos
- Hoje: "Desenvolvedor Java I", "Nível 1", "entry level" → sem `SENIORITY_MATCH:junior`
  (ficam `CONDITIONAL`); "Trainee" → `AMBIGUOUS`; "Java Júnior/Pleno" → `EXCLUDE`.
- Esperado: reconhecer `jr`, `jr.`, `junior`, `júnior`, `nível 1`, ` I ` (algarismo romano
  isolado após o cargo), `entry level`, `iniciante`, `trainee`, `aprendiz` como júnior/estágio.
  "Júnior/Pleno" e "Jr/Pl" → `CONDITIONAL` (não `EXCLUDE`). `pleno`/`senior` sozinhos continuam
  `EXCLUDE`.
- Cuidado com falsos positivos: "Senior" contendo " I"? "Analista II" é pleno, não júnior.
- Pronto quando: testes parametrizados cobrindo todos os exemplos acima, incluindo os negativos.

### 1.3 `workplace_model` é `UNKNOWN` em 100% das vagas
- Extrair de título/local/resumo: `REMOTE` ("remoto", "home office", "100% remoto"), `HYBRID`
  ("híbrido"), `ONSITE` ("presencial"). Ambiguidade → `UNKNOWN`. Evidência mínima registrada em
  `eligibility_notes`/`evidence_snippets`.
- Pronto quando: fixtures de Nerdin ("CLT • Senior • Home Office"), casado-dev ("Remoto (Sede em
  Campinas, SP)") e Infojobs ("Presencial (39)") geram o modelo correto e o classificador usa o
  valor para `workplace_confirmed`.

### 1.4 Títulos inúteis e ruidosos
- CIEE devolve só "Estágio"; Nube devolve "Técnica - 386089". O filtro não tem o que avaliar.
  Usar área/curso/atividade como parte do título (`title` ou `description_summary`) nessas
  fontes.
- 191 títulos têm ruído: selo "Nova" (Nerdin), sufixos com `|`, espaços. Limpar no
  `extract_value`/`make_record` sem perder informação de senioridade.
- Pronto quando: teste de limpeza de título (Nerdin com "Nova"), e CIEE/Nube com título
  descritivo em fixtures.

---

## P2 — Dados que nunca são preenchidos

Preenchimento atual: `seniority` 0%, `technologies` 0%, `requirements` 0%, `published_at` 0%,
`company` 62%, `location` 87%.

- 2.1 Gravar em `seniority` e `technologies` o que o classificador já detecta
  (`SENIORITY_MATCH:*`, `TECH_MATCH:*`). Não inventar: só valores com evidência.
- 2.2 `published_at`: Nerdin traz `<time datetime>`; mytechjobs traz "há N dias"; Indeed/Gupy
  podem trazer data relativa. Converter para ISO 8601 e gravar `null` quando não houver.
- 2.3 `company`: melhorar seletores onde falta (empregos-com usa `h3 a`; trampos `h5`;
  gupy/nube/ciee/infojobs conferir com fixtures).
- 2.4 Painel (`web/app.js`): ordenar por data (`published_at`) e mostrar "Nova" (já existe para
  `STATUS:NEW`).
- Pronto quando: `output/vagas.jsonl` de fixtures traz os campos preenchidos onde há evidência,
  o JSON Schema (`schemas/`) continua válido e o painel ordena por data.

---

## P3 — Fluxo e eficiência da coleta

### 3.1 Fontes ruidosas
- Nube (~924 vagas) e Infojobs (~1.028) somam ~65% do volume, quase tudo irrelevante, e
  consomem a maior parte do tempo. Restringir por área de TI na URL de partida ou `query_path`.
- Nube tem ~3.500 vagas; a rolagem está limitada a 40 iterações (≈1.200 mais recentes),
  `PARTIAL` por escolha. Manter o limite; documentar.

### 3.2 Detecção de portal quebrado
- Usar o histórico (`history.py`) para gravar a contagem por fonte por execução e avisar quando
  uma fonte cair mais de 50% em relação à média das últimas coletas, ou passar a zero. Registrar
  em `relatorio-execucao.json` (`warnings`) e mostrar no painel.
- Pronto quando: teste com histórico simulado dispara o aviso; sem histórico não dispara.

### 3.3 Deduplicação entre fontes
- 85 vagas repetidas (mesmo título + empresa) entre portais. Hoje só há anotação de candidatos.
  Agrupar e manter a versão da fonte mais confiável (Gupy/site da empresa > agregadores),
  preservando `also_seen_in` (lista de fontes).
- Pronto quando: teste com duas fontes e mesma vaga mantém uma e lista as fontes.

### 3.4 Alerta e integração
- Alerta de vaga `READY` nova (notificação do Windows, opcional e desligável).
- Exportar `READY`/`CONDITIONAL` novas para CSV pronto para importar no funil do usuário.
  **Não acessar SQLite/Notion do funil** (regra do projeto).

### 3.5 Paginação ainda não verificada
- `estagiotrainee` (Wix): só 16 vagas; scroll estável em 16, mas um teste isolado com
  `mouse.wheel` chegou a 29. Investigar carregamento preguiçoso.
- `ciee`, `mytechjobs`, `trampos`, `coodesh`: `PAGINATION_UNVERIFIED`. mytechjobs aceita
  `?page=N` mas não expõe link "próxima": avaliar opção `page_param` incremental em
  `PaginatedAdapter`.
- `programathor` termina `PARTIAL/EMPTY_PAGE_AFTER_RECORDS` mesmo quando chegou ao fim (da
  página 2 em diante só há vagas encerradas). Tratar como fim legítimo quando a página seguiu um
  link `next` real e só tem cards encerrados.
- `vagas-com`, `gupy`, `infojobs`: `QUERY_SWEEP_PARTIAL` (limite de páginas por termo e buscas que
  retornam vazio/timeout). Classificar busca vazia como `EMPTY`, não erro; o Infojobs dá timeout
  do `wait_selector` quando a busca não tem resultado.

### 3.6 Fontes candidatas ainda não testadas
APInfo, ABRE, IEL, Universia e o repositório `alinebastos/vagas-junior-estagio` (lista em
markdown; exigiria um coletor de README). Fontes **descartadas** (não readicionar): GeekHunter,
TalenTI, eu.dev.br, ViUmaVaga, Super Estágios, Futura Estágios, Glassdoor (`robots.txt`
bloqueia), GitHub `backend-br/vagas` (`robots.txt` nega `/issues`), Catho (login/anti-bot),
Revelo (404), Quero Vagas Tech / VagasPraJr / EmpregosTech (domínio não resolve; endereços a
confirmar com o usuário).

---

## P4 — Organização do código

- 4.1 `src/job_radar/fetching.py` (692 linhas) mistura política de coleta, `robots.txt`, detecção
  de bloqueio e ações de navegador. Separar em módulos (ex.: `robots.py`, `blocks.py`,
  `browser_actions.py`) sem mudar comportamento; os testes atuais devem continuar passando.
- 4.2 `src/job_radar/sources/base.py` (539 linhas) mistura paginação, criação de registro e
  fallback adaptativo. Separar `pagination`, `records`, `adaptive_guard`.
- 4.3 Pastas `.tmp-*` (12) e `debug.log` dentro do projeto: estão no `.gitignore`, mas geram erros
  de permissão em ferramentas. Não versionar; documentar limpeza no README.
- 4.4 **Testes de regressão com dados reais**: salvar uma fixture sanitizada (apenas trechos
  necessários, sem scripts/cookies/dados pessoais) de cada um dos 21 portais e um teste que rode o
  adaptador sobre ela. Uma mudança de layout hoje só aparece na coleta.
- 4.5 CI no GitHub Actions: Python 3.13, instalar Scrapling, rodar a suíte (excluir os testes que
  dependem de `.git` do vendor ou fornecer o clone).
- 4.6 README: separar "uso rápido" de "referência" (está longo) e listar as opções de
  `sources.yaml` (`single_page`, `browser.scroll_to_load`, `query_path`, `query_param`,
  `default_country`, `adaptive`).

---

## O que já foi feito (não refazer)

Fallback adaptativo só na 1ª página com validação (sem vagas falsas "CLT"/"Entrar");
`default_country: BR` em todas as fontes; `single_page`; `browser.scroll_to_load`;
`query_path`/`query_param` (vagas-com, infojobs, remotar); histórico `STATUS:NEW`
(`%LOCALAPPDATA%\JobRadar\history.json`, `--no-history`); enriquecimento pela página de detalhe
(`--enrich-limit`, rótulo `ENRICHED:DETAIL`); coleta paralela (`--workers`); 21 portais
habilitados.

## Ordem sugerida

P1 (1.1 → 1.2 → 1.3 → 1.4) → P2 → P3.2/3.3/3.1 → P4.4/P4.5 → P4.1/4.2 → restante.

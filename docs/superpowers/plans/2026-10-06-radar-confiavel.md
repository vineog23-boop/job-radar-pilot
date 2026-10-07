# Radar confiável Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Tornar confiável e simples o fluxo de descoberta, seleção, acompanhamento e exportação de vagas no Mac e Windows.
**Architecture:** Evoluir os módulos Python e painel existente. Manter contratos compatíveis; seleção exata da tabela por URLs canônicas e verificação conservadora usando FetchPolicy. Implementar sequencialmente com testes de regressão e revisão por tarefa.
**Tech Stack:** Python 3.13, Scrapling 0.4.15, HTTPServer, JavaScript sem framework, pytest, Playwright, Ruff.
**Spec:** docs/superpowers/specs/2026-10-06-radar-confiavel.md

## Global Constraints

- Python >=3.13,<3.14; Scrapling==0.4.15; não editar vendor/.
- Não alterar config/profile.yaml nem dados pessoais reais durante testes.
- Não raspar LinkedIn nem contornar robots, CAPTCHA ou login; respeitar intervalos.
- Preservar launchers Windows e preferências antigas; JSONL validado pelo schema existente.
- Compartilhar OutputLock em todas as mutações de vagas; ocupado retorna HTTP 409.
- Corrupção do acompanhamento impede limpeza e reescrita destrutiva.
- Interface, documentação e commits em português brasileiro; não versionar dados/exportações do usuário.
- Testes isolados; executar avaliação do classificador antes/depois sem alegar acurácia sem amostra rotulada.
- Trabalhar em feat/radar-confiavel; não publicar nem mesclar em main automaticamente.

## Review Focus

- Coleta falha após outra aba salvar uma vaga: preservar registro completo e status.
- Filtro ativo com mais de 300 vagas: exportar seleção inteira, ordenada, sem registros extras.
- Página 200 redirecionada para início/login: UNKNOWN, nunca confirmação.
- Troca de perfil durante coleta: HTTP 409 sem mudança parcial de preferências.
- Histórico salvo antigo e uso apenas por teclado: acessível sem perder foco.

### Task 1: Preservação e acompanhamento atômico

**Files:** modificar job-radar-pilot/src/job_radar/{output.py,cli.py,tracking.py,output_lock.py}; testes tests/{test_output.py,test_cli.py,test_tracking.py} e arquivo novo tests/test_preservation_regressions.py se necessário.
**Interfaces:** consumir write_outputs(...keep_urls,partial_sources); preservar assinatura. TrackingStore.set_status conserva retorno dict. Produzir leitura-modificação-gravação serializada por arquivo, entre threads/processos, sem aninhar OutputLock do diretório de vagas.
- [ ] Escrever regressões: SAVED antigo + EMPTY mantém registro e observed_at; full BLOCKED/PARTIAL preserva anteriores; fonte SUCCESS substitui somente não acompanhadas; novo URL vence antigo; JSONL corrompido recusa overwrite; duas gravações simultâneas mantêm ambas URLs/notas.
- [ ] Executar testes novos antes da implementação e registrar falhas esperadas.
- [ ] Corrigir carry-forward independentemente de merge_unrefreshed para tracked/incomplete; reconsultar tracking ao final da coleta; fail-safe se corrupção e não apagar arquivos anteriores. Garantir cesto/relatório sem duplicatas.
- [ ] Executar testes focados e suite; reportar comandos/resultados; commit fix em PT-BR.

### Task 2: Exportação exata e política temporal

**Files:** modificar src/job_radar/{webapp.py,auto_export.py,xlsx_export.py}; src/job_radar/web/app.js; testes tests/test_webapp*.py, tests/test_auto_export.py e novo tests/test_export_selection.py conforme convenções existentes (prefixos job-radar-pilot/).
**Interfaces:** produzir POST /api/export/{csv,markdown,xlsx,ai} com JSON {urls: string[], output_version: string} ordenado, máximo 20000 entradas e corpo máximo 2 MiB; registros resolvidos exclusivamente da saída local. URL inexistente/saída alterada retorna 409; duplicadas ou inválidas 400. Manter exports GET existentes. O frontend usa filteredJobs() completo antes de limitar linhas e envia apenas canonical_url e a output_version da tela. Formatos preservam ordem; seleção vazia permite arquivo vazio, sem fallback geral.
- [ ] Testes RED para seleção ordenada com remoto/período/atividade e 301 registros, seleção vazia, URL ausente/duplicada, todos formatos, e melhor exportação sem vaga com prazo vencido mesmo sem max_age_days.
- [ ] Implementar rota limitada, guardas locais existentes, downloads Blob com nome do servidor e erro visível. Exportação automática best exclui CLOSED; janela temporal e job_score usam dias fracionários consistentes com JS (total_seconds()/86400).
- [ ] GREEN focado e suíte; commit fix em PT-BR.

### Task 3: Disponibilidade com evidências e verificação no painel

**Files:** modificar src/job_radar/{link_check.py,activity.py,webapp.py,output.py}; web/{app.js,index.html}; tests/test_link_check.py, tests/test_activity.py, tests/test_webapp*.py.
**Interfaces:** manter classify_page_text(text) e check_canonical_url(url,source,fetcher) compatíveis, permitir expected_title opcional. LINK_CHECKED_AT entre agora e 7 dias atrás informa atividade: DEAD=CLOSED; LIVE=ACTIVE_CONFIRMED quando prazo não vencido e possui LINK_CHECK_METHOD:JOB_DETAIL_V2. Produzir esse marcador nas verificações novas; LIVE legado sem marcador não confirma disponibilidade (o algoritmo anterior só media comprimento da página); verificação velha ou futura não confirma. POST /api/verify-links inicia background limitado a 80 melhores vagas; GET /api/state fornece verification {status,checked,total,error,counts}; OutputLock cobre leitura/verificação/escrita. 409 em coleta/verificação/mutação concorrente; frontend oferece botão e progresso. Verificação respeita FetchPolicy e exclusões existentes. Ao reencontrar mesmo canonical_url, write_outputs preserva LINK/LINK_CHECKED_AT/LINK_CHECK_METHOD anteriores se o registro novo não trouxe verificação, sem renovar timestamp e sem carregar FIT antigo; nova verificação substitui a anterior.
- [ ] RED: institucional longo/login/CAPTCHA→UNKNOWN; candidatura com título/evidência específica→LIVE; removida/404→DEAD quando fetch realmente autorizado; prazo vencido vence LIVE; LIVE sem publicação é confirmado se recente; verificação antiga/futura e LIVE legado não confirmam; API ocupada 409, falha libera lock, resultado conserva tracking/observed_at; nova coleta mesmo URL não apaga verificação recente nem carrega aderência antiga.
- [ ] Implementar confirmação conservadora exigindo sinais de vaga e candidatura/JobPosting e identidade quando disponível; não supor 200=LIVE. Tornar status claros no painel, explicando UNKNOWN. Não adicionar requests externos aos testes.
- [ ] GREEN focado e suíte; commit feat em PT-BR.

### Task 4: Stack principal e perfil coerente

**Files:** modificar src/job_radar/{models.py,preferences.py,profiles.py,presets.py,classifier.py,fit.py,webapp.py}; web/{app.js,index.html}; tests/test_preferences.py, tests/test_profiles.py, tests/test_classifier.py, tests/test_webapp*.py.
**Interfaces:** adicionar primary_technologies: tuple[str,...]=() a SearchProfile/SearchPreferences, campo JSON opcional validado como technologies. Vazio conserva comportamento anterior. Quando configurado, ao menos uma principal deve ter evidência real no texto/tecnologias para READY; tecnologias complementares não substituem principal. Outra linguagem inequívoca continua OTHER_STACK; ausência de evidência suficiente resulta AMBIGUOUS/CONDITIONAL explicada, respeitando exclusões/nível/local. Usar matcher/aliases existentes, não substring Java=JavaScript. API save/activate perfis reclassifica com OutputLock antes de confirmar; ocupado não grava preferência/perfil parcialmente.
- [ ] Avaliar baseline e guardar em scratch. RED: Java principal+Spring complemento combina com Java/Spring júnior; Python+SQL não READY; JavaScript não Java; Java sênior excluída; principal ausente explicada; prefs legadas roundtrip. Ativar perfil Python sobre Java atual reclassifica sem perder LINK labels ou tracking; coleta ocupada não muda disco.
- [ ] Implementar campo visível de stack principal e tecnologias complementares; presets fornecem escolhas coerentes; edição salva/ativação atualiza resultados e mensagem de perfil aplicado. Não alterar profile.yaml.
- [ ] GREEN focado e suíte; avaliação depois descreve distribuição/diferenças e falta de ground truth; commit feat em PT-BR.

### Task 5: Organização, histórico e interação

**Files:** modificar src/job_radar/{webapp.py,tracking.py}; web/{app.js,index.html,styles.css}; tests/test_webapp*.py, tests/test_tracking.py.
**Interfaces:** manter filtros e atalhos existentes; cliques Salvas/Em processo limpam filtros conflitantes de texto/source/match/quick/age/activity para mostrar histórico inteiro (age vazio, activity all); refinamento posterior permitido. /api/state inclui tracking_version e tracking completo se mudou desde parâmetro tracking_since; versão e conteúdo são lidos juntos sob transação para não marcar um snapshot velho como novo; frontend sincroniza sem perder foco. API de acompanhamento valida presença da URL canônica sob a mesma transação de tracking antes de confirmar SAVED; URL que saiu da saída desde a tela retorna 409 com orientação recarregar, sem tracking órfão. A transação Task1 não é reentrante: adaptar com validação dentro da operação atômica ou reentrância segura, nunca aninhar cegamente. Progress {finished,total} extrai linha PROGRESS e não confunde lidas/salvas. localStorage radar.selectedSources memoriza portais por códigos ainda válidos.
- [ ] RED com testes reais defaults: salva de 90 dias aparece no atalho; aplicação em outra aba atualiza painel; foco de detalhes/status permanece após render; seleção lembrada; coleta com PROGRESS mostra total; filtros exatos exportam além da primeira página usando Task 2.
- [ ] Implementar restauração de foco por URL e tipo de controle (ou patch de linha), estados vazios explicativos, contagem/histórico e progresso honesto. Separar filtros de período e atividade: age e max_age_days avaliam somente publicação válida, permitindo activity=closed+age30 incluir vaga encerrada publicada há2dias; recomendações best/fit conservam política explícita contra CLOSED. Atualizar testes legados conflitantes com essa semântica. Adicionar opção de período Sem data de publicação e ação visível quando há vagas sem data ocultas; não fabricar published_at com observed_at e permitir examinar essas vagas removendo conflito de atividade. Corrigir checkbox width/height e foco visível. Evitar reconstrução visual ampla.
- [ ] GREEN focado e suíte; commit feat em PT-BR.

### Task 6: Mac, documentação e validação integrada

**Files:** criar src/job_radar/user_paths.py, scripts/setup-mac.sh e Radar de Vagas.command versionado; modificar preferences.py/tracking.py/history.py para caminho compartilhado, fetching.py/adaptive.py para perfis/cache nativos, webapp.py abrir pasta; job-radar-pilot/README.md, docs/MELHORIAS-PENDENTES.md, .github/workflows/tests.yml; testes tests/test_user_paths.py, tests/test_webapp*.py e testes de fetching/adaptive para defaults nativos.
**Interfaces:** user_data_dir()->Path respeita LOCALAPPDATA primeiro; macOS ~/Library/Application Support/JobRadar; Windows fallback atual; Linux XDG_DATA_HOME/job-radar ou ~/.local/share/job-radar. open export via subprocess.Popen([open,path]) macOS, os.startfile Windows, xdg-open Linux sem shell. Launcher usa localização própria, Python3.13 venv, proteção porta e log legível; setup preserva dados e checa versão/Scrapling pin. Windows scripts mantidos.
- [ ] RED para caminhos/env e abrir pasta Mac (mock somente subprocess); setup/launcher syntax e versão apropriados; teste defaults idade/atividade integrado sem depender seed autouse legado.
- [ ] Implementar scripts macOS reexecutáveis, CI matrix windows-latest/macos-latest; documentar perfis, disponibilidade, salvas/histórico, exportação exata, dados/backup, operação Mac. Atualizar backlog com mudanças entregues e limitações reais.
- [ ] Executar suíte completa, Ruff, pip check, comparação classificador; relatar evidências/limites. Commit feat em PT-BR. Coordenador faz validação visual CUA e aplica versão instalada apenas depois da revisão completa.

### Task 7: Fontes públicas InHire, CI&T e Greenhouse

**Files:** modificar job-radar-pilot/config/sources.yaml; src/job_radar/{models.py,config.py,pipeline.py,enrich.py,link_check.py,webapp.py}; sources/{base.py,generic.py,dynamic.py,json_api.py}; web/app.js; tests/test_new_portals.py e fixtures/new-portals/*; README e docs/MELHORIAS-PENDENTES.md. Modificar somente arquivos necessários pelos contratos; não refatorar adaptadores sem relação.
**Interfaces:** SourceConfig.default_company: str|None=None e fetch_details: bool=True, com validação. default_company preenche empresa somente quando explicitamente cadastrada e ausente no cartão; fetch_details false impede TODOS os fetches de detalhes em enrich_records e verify_records, sem mudar acesso manual aos links. Adicionar api.page_mode=single: page_url(config,index) conserva start_url exatamente e JsonApiAdapter faz uma única requisição; page_param não obrigatório nesse modo, total_path opcional para conferir total declarado, sem total/page/offset inventados. Contratos paginados antigos intactos.
- [ ] Ler pesquisa e fixtures sanitizadas de .superpowers/sdd/2026-10-06-radar-confiavel/portal-research/report.md; confirmar fontes oficiais/robots. RED: InHire DOM renderizado produz títulos/URLs/UUID IDs estáveis e empresa correta (H1 vazio Bionexo); shell SPA sem cards é ERROR, não EMPTY; bloqueio/login gera bloqueado; mudança slug conserva identidade por UUID; CI&T links diferentes com UUID query não colapsam e nenhuma chamada a detalhes ocorre; Greenhouse single chamada exata sem paginação espúria, metadata total incompatível retorna PARTIAL, jobs ausente é ERROR, jobs[] total0 é EMPTY, campos/datas/schema preservados.
- [ ] Implementar quatro fontes enabled=true: inhire-programmers start_url https://programmers.inhire.app/vagas, inhire-bionexo https://bionexo.inhire.app/vagas (kind dynamic, adaptive false, max_pages1, intervalo3, company explícita, sem queries inventadas; lista observada sem paginação, detecção de limites se houver); ciandt https://ciandt.com/br/pt-br/carreiras/oportunidades (generic, max_pages1, intervalo3, company CI&T, fetch_details=false, sem default_country BR porque vagas globais); greenhouse-abinbev https://boards-api.greenhouse.io/v1/boards/abinbev/jobs?content=true (json single, total_path meta.total, campos do relatório oficial, sem default_country BR, tech_focus=false porque board corporativo). Nomes legíveis por empresa, sem vender cobertura de todo ATS.
- [ ] InHire IDs extraídos do UUID /vagas/UUID/slug; CI&T ID UUID opportunity; adaptar identity.job_id_from_url se necessário com regressões e sem afetar outros portais. Extrair só geografia/modelo evidenciados; published desconhecido permanece None. Usar selectors estáveis públicos das fixtures. Não chamar api.inhire.app (robots403) diretamente; navegação normal dinâmica nas páginas públicas permitidas. Se limite/paginação não comprovado, PARTIAL em vez de completude falsa.
- [ ] GREEN offline focado e suíte; smoke live somente das quatro listagens com output/prefs/history isolados (sem enriquecer 181 detalhes), registrar contagens/status e erros reais. Se uma integração falhar live, corrigir com evidência ou deixá-la desabilitada e explicada. Documentar alcance por empresa, ausência de publicação em algumas páginas, CI&T detalhes manuais, 99Freelas projetos freelance separado e Telegram depende de canal público fornecido. Preservar LinkedIn manual e não duplicar Nerdin/Gupy/GeekHunter/Quickin. Commit feat em PT-BR e report.

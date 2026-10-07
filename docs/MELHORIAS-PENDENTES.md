# Job Radar Pilot — revisões e melhorias pendentes

Backlog para o Claude Code (nuvem ou local). Atualizado em **01/10/2026**, depois das sessões que
adicionaram: fontes por API/RSS (Gupy API, Primeira Vaga Tech, Empregos Tech), LinkedIn seguro
(links + importação), exportação `.xlsx`, menu Limpeza com desfazer, 25 stacks + stacks próprias,
palavras-chave/empresas/contrato/inglês, reaplicação do perfil às vagas salvas, gerador de termos
da área (até 20 termos) e pausar/parar a busca. Suíte: **~775 testes passando** (CI verde de
novo desde 01/10/2026; ver "Revisão geral de 01/10/2026" no fim).

Leia antes o `CLAUDE.md` da raiz (setup, regras e armadilhas). Regras rápidas: plano antes de
código, teste antes da implementação, um commit por item, branch + PR, README atualizado quando
o usuário perceber a mudança, e marcar aqui o que foi feito.

---

### Radar confiável — 06/10/2026

- [x] Exportação exata da tabela em CSV, Markdown, XLSX e texto para IA: seleção
  completa, ordem e versão carregada, sem fallback quando vazia; downloads do
  painel de exportação continuam com filtros independentes.
- [x] Melhores vagas e exportação automática excluem vagas encerradas sem exigir
  janela temporal; recência calculada com dias fracionários e sem datas futuras.

- [x] Acompanhamento protegido na coleta e limpeza, falha segura diante de
  corrupção e transações que preservam mudanças concorrentes.
- [x] Disponibilidade com evidências: detalhe confirmado, listagem recente,
  encerrada e não comprovada; verificação em segundo plano com progresso e trava.
- [x] Perfis normalizados e reaplicação atômica; conflito retorna 409 sem salvar
  configuração parcial. Seletores de Salvas/Em processo expõem também histórico.
- [x] Dados locais nativos Windows/macOS/Linux, prioridade de LOCALAPPDATA,
  abertura de exportações sem shell, setup e launcher macOS reexecutáveis.
- [x] CI configurada em matriz Windows/macOS com Python 3.13, Scrapling 0.4.15,
  suíte offline, Ruff e pip check. A execução remota depende do próximo push/PR.
- [x] Ativar novas fontes após validação: InHire por empresa (Programmers/Bionexo),
  CI&T somente listagem/manual e Greenhouse por board (AB InBev). Pesquisa pública
  concluída; nenhuma cobertura global desses ATS é prometida.
- [ ] 99Freelas em categoria freelance separada; Telegram depende de canais
  públicos fornecidos. LinkedIn permanece exclusivamente pesquisa/importação manual.
- [ ] Coordenador: revisão completa, validação visual e instalação do launcher
  no ambiente do usuário; esta etapa mantém o atalho instalado sem alterações.

## Dados reais para trabalhar sem acessar os portais

`job-radar-pilot/tests/fixtures/amostra-real-2026-10-01.jsonl` — **300 vagas reais** da coleta de
01/10/2026 (90 `READY`, 80 `CONDITIONAL`, 130 `AMBIGUOUS`), com descrição cortada em 600
caracteres. Perfil usado: estágio/júnior, Java + Spring Boot, remoto Brasil + São Carlos/SP +
Grande Florianópolis/SC. Use para medir o classificador e criar testes de regressão.

Retrato da coleta completa (1.157 vagas de TI úteis, 17 portais com resultado):

| Faixa | Vagas | Observação |
|---|---|---|
| READY | 93 (8%) | "Mais compatível" |
| CONDITIONAL | 182 (16%) | tem a stack, falta confirmar nível/local/modelo |
| AMBIGUOUS | 882 (76%) | **ver item 1.1** — a maioria é de TI, só que de outra stack |

Volume por portal: empregostec 496, primeiravagatech 333, remotar 93, seja-trainee 52, nerdin 38,
indeed 34, geekhunter 22, infojobs 20; os demais abaixo de 20.

---

## P1 — Qualidade do match (maior impacto para o usuário)

### ✅ 1.1 "Dados insuficientes" está escondendo "outra stack" — FEITO em 01/10/2026
- Feito: `FIT:OTHER_STACK` + `OTHER_STACK:<stack>`, filtro "Outra stack" no painel; "backend",
  "api rest" etc. deixaram de ser stack principal quando o perfil tem tecnologia específica
  (11% das READY da amostra eram Python/Node/.NET). Amostra: READY 94→73, OTHER_STACK 0→66.

Texto original:
- Evidência: dos 882 `AMBIGUOUS`, 432 já têm nível compatível e 291 têm local compatível, mas só
  36 têm `TECH_MATCH`. Exemplos: "Desenvolvedor Python Junior Remoto", "Front-end Junior React".
  São vagas de TI **de outra stack**, não vagas sem dados. 250 não têm descrição.
- Proposta: separar `AMBIGUOUS` em dois rótulos explicáveis: `FIT:OTHER_STACK` (sinais de TI
  claros, nenhuma tecnologia do perfil) e `FIT:AMBIGUOUS` (poucos dados de verdade: cargo
  genérico, sem descrição). Painel: filtro "Outras stacks" e motivo "stack diferente da sua".
  Cargos genéricos ("Engenheiro de software Júnior", "Analista de sistemas Júnior") continuam
  ambíguos e são bons candidatos ao enriquecimento pela página de detalhe.
- Cuidado: `FIT:` é lido por cleanup, export, xlsx, app.js e testes. Mapear todos os usos antes.
- Pronto quando: na amostra real, as vagas Python/React/PHP de perfil Java saem como
  `OTHER_STACK`; os cargos genéricos sem stack continuam `AMBIGUOUS`; testes parametrizados.

### ✅ 1.2 Aliases de tecnologia — FEITO em 01/10/2026
- Feito: apelidos nos dois sentidos e limites rígidos para termos curtos (go/js/r/c), mais
  inglês "diferencial" só na mesma frase, contrato negado e "redes sociais".

Texto original:
- O usuário escreve "springboot", "spring-boot", "js", "k8s", "node.js", "nodejs", "c sharp".
  Hoje o casamento é literal (com hífen/espaço flexível). Criar uma tabela de aliases
  (`springboot`↔`spring boot`, `node`/`nodejs`/`node.js`, `javascript`/`js`, `kubernetes`/`k8s`,
  `postgres`/`postgresql`, `c#`/`csharp`/`.net`?), aplicada às tecnologias do perfil, às
  palavras-chave e ao texto da vaga.
- Pronto quando: teste com cada alias casando nos dois sentidos, sem falso positivo ("js" não
  casa com "jsp"; "go" não casa com "google" nem com "go-live").

### ✅ 1.3 Aprender com o que o usuário salva e descarta — FEITO em 07/10/2026
- Feito: `reclassify.tracking_insights()` cruza `vagas.jsonl` com `tracking.json`
  (salva/aplicada/entrevista/oferta = sinal positivo; descartada = negativo; recusada pela
  empresa não conta para nenhum lado) e sugere empresas/tecnologias só quando o sinal é claro
  (aparece pelo menos `min_count` vezes de um lado e menos vezes do outro; empate não sugere).
  Nunca aplica sozinho: `/api/tracking/insights` devolve a evidência (contagem dos dois lados) e
  o painel mostra chips — igual ao padrão já usado em "Aparecem muito nas suas vagas" — perto de
  Diferenciais, Proibidas, Empresas a evitar e Empresas favoritas; o clique é que adiciona.
- Testado: 7 testes novos da função pura (`tests/test_tracking_insights.py`) + 1 teste de API
  (`test_api_tracking_insights`); suíte inteira (1093 testes) e Ruff continuam verdes.
- **Não verificado visualmente** no painel real: havia um processo já rodando com dados reais do
  usuário na porta 8765, e reiniciá-lo para testar exigiria derrubar o painel que ele pode estar
  usando. Reabra pelo atalho (mata o processo antigo e carrega o `app.js` novo) para ver os chips.

### ✅ 1.4 Medir o classificador — FEITO em 01/10/2026 (falta o gabarito humano)
- Feito: `job-radar avaliar` (`src/job_radar/evaluation.py`) com `--salvar`/`--base` e
  `--gabarito`. Base de antes do P1: `tests/fixtures/avaliacao-base-antes-p1.json`.
- **Pendente do usuário**: preencher a coluna `esperado` de `tests/fixtures/gabarito-amostra.csv`
  (60 vagas). Sem isso a ferramenta mede mudança, não acerto.

Texto original:
- Script `job-radar-pilot/tools/avaliar_classificador.py` (ou comando `job-radar avaliar`) que
  roda o classificador na amostra real e imprime a distribuição por faixa, por portal e os
  motivos mais comuns, para comparar antes/depois de cada mudança do P1.
- Pronto quando: o PR de cada item do P1 mostra o "antes × depois" da amostra.

### 1.5 Títulos inúteis (ainda aberto)
- CIEE devolve só "Estágio"; Nube devolve "Técnica - 386089". Usar área/curso/atividade como
  parte do título ou da descrição nessas fontes. Precisa de fixture real (ver 2.1).

---

## P2 — Fontes e coleta

### 2.1 Fixtures sanitizadas por portal (regressão de layout)
- Hoje uma mudança de layout só aparece na coleta. Salvar o trecho mínimo do HTML/JSON/RSS de
  cada portal habilitado (sem scripts, cookies ou dados pessoais) e um teste por adaptador.
  Na nuvem não há acesso aos portais: peça ao usuário para rodar um script local que gera as
  fixtures (escreva o script; não rode coleta na nuvem).

### 2.2 Fontes por empresa via APIs públicas de vagas
- Muitas empresas publicam vagas em boards com API pública e estável (ex.: Greenhouse
  `boards-api.greenhouse.io/v1/boards/<empresa>/jobs`, Lever `api.lever.co/v0/postings/<empresa>`,
  e páginas Gupy de empresas). O adaptador `kind: json` já suporta mapeamento de campos.
  Proposta: lista "empresas monitoradas" em `sources.yaml` (ou no painel) gerando uma fonte por
  empresa. Conferir `robots.txt`/termos de cada provedor antes.
- Pronto quando: teste com resposta JSON de exemplo de cada provedor; documentação no README.

### ✅ 2.3 Saúde e rendimento por portal — FEITO em 01/10/2026 (sem tempo por portal ainda)
- Registrar por coleta e por portal: consultas feitas, tempo, vagas lidas, vagas úteis e
  bloqueios. Mostrar no painel "rendimento" (úteis por consulta) para o usuário desligar portais
  que só gastam tempo (ex.: o que trouxer quase só `OFF_TOPIC`).

### 2.4 Pendências antigas ainda abertas
- Paginação não verificada: estagiotrainee (Wix, lazy load), ciee, mytechjobs (`?page=N` sem link
  "próxima" → opção `page_param` incremental), trampos, coodesh; busca vazia no Infojobs vira
  timeout em vez de `EMPTY`.
- Candidatas não testadas: APInfo, ABRE, IEL, Universia. **Descartadas, não readicionar**:
  GeekHunter (exceto o que já existe), TalenTI, eu.dev.br, ViUmaVaga, Super Estágios, Futura
  Estágios, Glassdoor, GitHub `backend-br/vagas`, Catho, Revelo, LinkedIn (scraping).

#### Investigado em 07/10/2026 (não mexer sem reabrir a discussão)

- **Nube — 0 úteis em 1.218 registros**: não é bug de URL. `/estudantes/vagas` é um board
  generalista (5.973 vagas de todas as áreas: engenharia, vendas, administrativo etc.); o filtro
  por área ("Tecnologia da Informação") só existe no JavaScript do cliente, lido de uma API JSON
  pública (`/api/portal/buscar_listagem_vagas?offset=&limite=`) sem parâmetro de categoria na URL.
  Medido ao vivo: de ~3.292 vagas lidas dessa API, só 15 eram de TI (~0,5%) — extrapolando para as
  5.973 totais, são ~27 vagas de TI no site inteiro, a maioria com título genérico
  ("Tecnologia da Informação - <id>", sem stack). Corrigir direito exigiria migrar o adaptador de
  `dynamic` para `json` e estender `sources/json_api.py` (hoje só lê listas; a API do Nube devolve
  `dict_por_id_vaga`, um dicionário por ID) — mudança em código compartilhado com outros portais
  `json`, para um ganho de poucas dezenas de vagas genéricas. **Recomendação**: não vale o risco;
  o aviso "este portal rende pouco" já existe no painel (`app.js` `renderSources`, quando
  `useful === 0` e `records >= 5`) e cobre o caso — deixar o usuário desmarcar Nube se quiser.
- **Programathor — `PARTIAL` mesmo "no fim legítimo"**: confirmado ao vivo que a busca
  `jobs-java` fica vazia a partir da página 6, mas o próprio site mostra um link "Last » page=230"
  na paginação (provavelmente o total do site inteiro, não da busca filtrada) e nenhuma página
  exibe texto de "nenhum resultado". Como não há sinal textual confiável de fim de busca, o
  adaptador genérico (`sources/base.py`, `EMPTY_PAGE_AFTER_RECORDS`) está certo em marcar
  `PARTIAL` em vez de supor `SUCCESS` — essa lógica é compartilhada por todos os portais
  `generic`, então "corrigi-la" para aceitar uma página vazia como fim legítimo arriscaria
  declarar coleta completa em portais que na verdade sofreram bloqueio temporário.
  **Recomendação**: manter como está; não é regressão, é limite real do portal.

---

## P3 — Painel e experiência

- ✅ 3.1 (FEITO 01/10: faixa "N vagas compatíveis novas que você ainda não viu", Ver só as
  novidades, Marcar como vistas; "vista" = aberta/expandida/marcada) **Resumo ao abrir**: "X vagas novas compatíveis desde a sua última visita" com atalho para
  filtrá-las (usa `STATUS:NEW` + data da última visita em `localStorage`).
- ✅ 3.2 (FEITO 01/10: Entrevista/Oferta/Recusada com data por etapa, faixa "Seu funil" e filtro
  Em processo; visão em colunas ainda não) **Funil de candidatura**: ampliar o acompanhamento (salva → aplicada → entrevista → oferta /
  recusada) com data de cada mudança e uma visão em colunas; exportar CSV. **Não** acessar o
  SQLite/Notion de outros projetos do usuário.
- 3.3 **Notificação** de vaga `READY` nova após a coleta agendada (Windows, desligável).
- ◐ 3.4 (PARCIAL 01/10: celular em cartões sem rolagem horizontal, foco visível; falta auditoria
  WCAG completa) **Acessibilidade e mobile**: auditoria WCAG AA (contraste, foco visível, navegação por
  teclado nos chips/etiquetas, `aria-pressed`/`aria-live`), e layout em tela estreita.
- ✅ 3.5 (FEITO 07/10: `scoreBreakdown()` no `app.js` separa os 20 pontos de cada critério
  confirmado — Tecnologia/Nível/Local/Modelo —, +10 de "Mais compatível", diferenciais/empresa
  favorita e o bônus de recência; o total nunca diverge do score real, mesmo em vagas antigas
  sem os rótulos individuais) **Explicar o score na tabela**: pontos de cada critério e
  diferenciais, visível ao abrir o detalhe da vaga.

---

## P4 — Código, desempenho e segurança

- 4.1 **`web/app.js` tem ~1.940 linhas** num arquivo só. Separar em módulos ES nativos (sem
  build): estado/API, tabela, preferências (etiquetas, stacks, termos), limpeza, exportação,
  LinkedIn, controle da busca. Sem mudança de comportamento; testes do painel intactos.
- 4.2 **`webapp.py` tem ~1.470 linhas**: `do_GET/do_POST/do_PUT` com cadeias de `if path ==`.
  Extrair uma tabela de rotas e módulos por assunto (preferências, exportação, limpeza, busca).
- 4.3 `fetching.py` (~710) e `sources/base.py` (~550): separar robots/bloqueio/ações de navegador
  e paginação/registro/fallback adaptativo (pendência antiga).
- ✅ 4.4 (FEITO 01/10: padrões e termos canônicos em cache; 6.000 vagas 8,5 s → 5,7 s)
  **Desempenho do classificador**: `_contains_term` monta a regex a cada chamada, para cada
  termo e cada vaga (a reaplicação do perfil roda isso milhares de vezes). Cachear os padrões
  compilados (`functools.lru_cache`) e medir antes/depois com a amostra real.
- ✅ 4.5 (FEITO 01/10: Host, Origin e JSON obrigatório em POST/PUT; nenhum endpoint aceita
  caminho de arquivo do cliente) **Segurança do servidor local** (`127.0.0.1:8765`): validar o cabeçalho `Host`
  (proteção contra DNS rebinding), exigir `Content-Type: application/json` também nos POST sem
  corpo (`/api/search/pause|resume|stop`) para que um site malicioso não consiga disparar ações
  por formulário cross-origin, e revisar se algum endpoint aceita caminho de arquivo vindo do
  cliente. Adicionar testes.
- 4.6 Qualidade estática no CI: `ruff` (lint/format) e checagem de tipos (`pyright` ou `mypy`)
  só nos módulos novos primeiro, sem quebrar o CI de uma vez.
- 4.7 README longo: separar "Uso rápido" (o que o usuário clica) de "Referência" (CLI, YAML, API).

---

## Revisões sugeridas (pedidos prontos para colar)

1. **Auditoria geral**: "Leia o CLAUDE.md e este backlog. Faça uma revisão do projeto inteiro
   (arquitetura, testes, bugs prováveis, segurança) e devolva uma lista priorizada de achados com
   arquivo e linha. Não altere código ainda."
2. **Classificador**: "Implemente o item 1.4 e use-o para avaliar a amostra real. Depois proponha
   e implemente 1.1 e 1.2, mostrando o antes × depois."
3. **Segurança**: "Faça o item 4.5 com testes e explique cada risco em linguagem simples."
4. **Organização**: "Faça 4.4, depois 4.2 e 4.1 sem mudar comportamento; um PR por item."
5. **Produto**: "Implemente 3.1 e 1.3."

## Ordem sugerida

~~1.4 → 1.1 → 1.2 → 4.4 → 4.5~~ (feitos) → gabarito humano do 1.4 (pendente do usuário) →
~~1.3~~ (feito) → 3.1 → 2.3 → 4.2 → 4.1 → 2.2 → restante.

## Já feito (não refazer)

Fallback adaptativo validado; `default_country`; `single_page`; `scroll_to_load`;
`query_path`/`query_param`; histórico `STATUS:NEW` e aviso de queda por fonte; enriquecimento
por página de detalhe; coleta paralela; dedupe entre portais (`ALSO_SEEN_IN`); `workplace_model`
inferido; sinônimos de júnior/estágio e faixa júnior/pleno; remoto com sede fora do escopo;
fontes `json`/`rss`; LinkedIn seguro (links + importação); export CSV/MD/XLSX/Texto para IA com
filtros; menu Limpeza (regras, prévia, backup, desfazer); perfis nomeados; 25 stacks + stacks
próprias; etiquetas; palavras-chave obrigatórias/diferenciais/proibidas; empresas
evitar/favoritas; contrato; inglês avançado; "Ver impacto" e reaplicação às vagas salvas;
gerador de termos da área (20 termos + estimativa de consultas); pausar/retomar/parar a busca;
CI no GitHub Actions.

## Revisão geral de 01/10/2026 (feito)

Achados da auditoria e o que foi corrigido (um commit por item, branch
`claude/beautiful-goldberg-de71gj`):

- CI vermelho desde 30/09: testes dependiam da pasta de execução → independem.
- Painel: CSRF (parar/pausar/desfazer por formulário de outro site) e DNS rebinding → Host,
  Origin e JSON obrigatório.
- `tracking.json` ilegível desligava a proteção das vagas salvas → poda desligada / 409.
- Coleta agendada × painel regravando o mesmo arquivo → `output/.radar-output.lock`, saída 5.
- Leitura do `FIT:` espalhada em 7 arquivos → `job_radar.fit`.
- Classificador gravava palpite em `technologies` → só exibição junta (`job_technologies`).
- Vagas podadas na coleta não voltavam ao ampliar o perfil → `vagas-descartadas-na-coleta.jsonl`.
- CSV com injeção de fórmula → `spreadsheet_safe`.
- `/api/state` relia e o painel redesenhava tudo a cada 5 s → `output_version` + `?since=`.
- P3: erro inesperado vira 500 com mensagem; limpar/desfazer/reaplicar recusam linha ilegível;
  `history.json` corrompido é guardado em cópia.

## Noite de 01/10/2026 (feito, autônomo)

- Extração: descrições sem JavaScript/CSS/anúncios (XPath só de texto visível) e sem restos de
  navegação; títulos sem códigos internos.
- Deduplicação: cargo/empresa normalizados, local compatível, republicações no mesmo portal
  (`REPOSTED:<n>`), URL acompanhada sempre fica. Amostra: 300 → 286 únicas.
- Exportação automática ao fim de cada coleta em Documentos\Radar de Vagas (configurável no painel).
- Painel: barra de trabalho (1 Buscar · 2 Revisar · 3 Exportar), novidades, filtros rápidos,
  Desfazer no acompanhamento, celular em cartões, progresso da busca, estado vazio que orienta,
  Configurar busca com resumo e filtros avançados recolhidos.
- Funil de candidatura e rendimento por portal.
- Testes isolados dos dados reais do usuário (`tests/conftest.py`).

Próximos passos sugeridos: preencher o gabarito (1.4) → 1.3 (aprender com salvas/descartadas) →
2.1 (fixtures por portal, gerar no PC) → 2.2 (APIs Greenhouse/Lever por empresa, verificar ao vivo
no PC) → 4.2/4.1 (quebrar webapp.py e app.js).

## Radar confiável — 06/10/2026

- [x] Preservação na coleta completa de vagas acompanhadas e fontes incompletas,
  mantendo `observed_at`; JSONL anterior ilegível impede publicação.
- [x] Acompanhamento com leitura-modificação-gravação serializada entre processos
  e threads; snapshot final da coleta sob a mesma transação.

### ✅ Stack principal e perfil coerente — 07/10/2026

- Principal explícita com alternativas e complementares; campo vazio mantém a
  classificação legada. Ausência de evidência recebe motivo visível.
- Salvar/ativar aplica o perfil às vagas sob a trava compartilhada; ocupado retorna
  409 antes de persistir. Falhas restauram arquivos anteriores; links, acompanhamento
  e observação são preservados. Preferências editadas atualizam o perfil ativo.
- Presets e sugestões preenchem principais sem apagar termos personalizados.

### ✅ Fontes públicas por empresa — 07/10/2026

- InHire — Programmers e Bionexo: páginas públicas renderizadas, UUID estável,
  empresa explícita e data desconhecida quando ausente; sem acesso direto à API.
- CI&T: listagem oficial global e links manuais; nenhum enriquecimento ou
  verificação automática de detalhes proibidos pelo robots.
- Greenhouse — AB InBev: API pública em chamada única, `first_published` e
  conferência de `meta.total`, sem país ou foco tecnológico presumidos.
- `fetch_details` e `default_company` validados; paginadores antigos preservados.
- 99Freelas segue como projetos freelance; Telegram aguarda canais públicos;
  LinkedIn segue manual. Não foram duplicadas fontes já existentes.

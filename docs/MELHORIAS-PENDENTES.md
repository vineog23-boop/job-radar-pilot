# Job Radar Pilot — revisões e melhorias pendentes

Backlog para o Claude Code (nuvem ou local). Atualizado em **01/10/2026**, depois das sessões que
adicionaram: fontes por API/RSS (Gupy API, Primeira Vaga Tech, Empregos Tech), LinkedIn seguro
(links + importação), exportação `.xlsx`, menu Limpeza com desfazer, 25 stacks + stacks próprias,
palavras-chave/empresas/contrato/inglês, reaplicação do perfil às vagas salvas, gerador de termos
da área (até 20 termos) e pausar/parar a busca. Suíte: **~630 testes passando**.

Leia antes o `CLAUDE.md` da raiz (setup, regras e armadilhas). Regras rápidas: plano antes de
código, teste antes da implementação, um commit por item, branch + PR, README atualizado quando
o usuário perceber a mudança, e marcar aqui o que foi feito.

---

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

### 1.1 "Dados insuficientes" está escondendo "outra stack"
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

### 1.2 Aliases de tecnologia
- O usuário escreve "springboot", "spring-boot", "js", "k8s", "node.js", "nodejs", "c sharp".
  Hoje o casamento é literal (com hífen/espaço flexível). Criar uma tabela de aliases
  (`springboot`↔`spring boot`, `node`/`nodejs`/`node.js`, `javascript`/`js`, `kubernetes`/`k8s`,
  `postgres`/`postgresql`, `c#`/`csharp`/`.net`?), aplicada às tecnologias do perfil, às
  palavras-chave e ao texto da vaga.
- Pronto quando: teste com cada alias casando nos dois sentidos, sem falso positivo ("js" não
  casa com "jsp"; "go" não casa com "google" nem com "go-live").

### 1.3 Aprender com o que o usuário salva e descarta
- O acompanhamento (`tracking.json`: SAVED/APPLIED/DISCARDED) é um rótulo humano grátis. Gerar
  sugestões: termos/empresas muito mais frequentes nas descartadas do que nas salvas →
  "Proibidas"/"Empresas a evitar"; o inverso → "Diferenciais"/"Favoritas". Só sugerir; o usuário
  clica para aplicar (mesmo estilo dos chips de "Aparecem muito nas suas vagas").
- Pronto quando: teste com tracking simulado gera sugestões coerentes e nada é aplicado sozinho.

### 1.4 Medir o classificador
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

### 2.3 Saúde e rendimento por portal
- Registrar por coleta e por portal: consultas feitas, tempo, vagas lidas, vagas úteis e
  bloqueios. Mostrar no painel "rendimento" (úteis por consulta) para o usuário desligar portais
  que só gastam tempo (ex.: o que trouxer quase só `OFF_TOPIC`).

### 2.4 Pendências antigas ainda abertas
- Nube/Infojobs: restringir à área de TI na URL de partida.
- Paginação não verificada: estagiotrainee (Wix, lazy load), ciee, mytechjobs (`?page=N` sem link
  "próxima" → opção `page_param` incremental), trampos, coodesh; programathor marca `PARTIAL` mesmo
  no fim legítimo; busca vazia no Infojobs vira timeout em vez de `EMPTY`.
- Candidatas não testadas: APInfo, ABRE, IEL, Universia. **Descartadas, não readicionar**:
  GeekHunter (exceto o que já existe), TalenTI, eu.dev.br, ViUmaVaga, Super Estágios, Futura
  Estágios, Glassdoor, GitHub `backend-br/vagas`, Catho, Revelo, LinkedIn (scraping).

---

## P3 — Painel e experiência

- 3.1 **Resumo ao abrir**: "X vagas novas compatíveis desde a sua última visita" com atalho para
  filtrá-las (usa `STATUS:NEW` + data da última visita em `localStorage`).
- 3.2 **Funil de candidatura**: ampliar o acompanhamento (salva → aplicada → entrevista → oferta /
  recusada) com data de cada mudança e uma visão em colunas; exportar CSV. **Não** acessar o
  SQLite/Notion de outros projetos do usuário.
- 3.3 **Notificação** de vaga `READY` nova após a coleta agendada (Windows, desligável).
- 3.4 **Acessibilidade e mobile**: auditoria WCAG AA (contraste, foco visível, navegação por
  teclado nos chips/etiquetas, `aria-pressed`/`aria-live`), e layout em tela estreita.
- 3.5 Explicar o score na tabela (tooltip com os pontos de cada critério e diferenciais).

---

## P4 — Código, desempenho e segurança

- 4.1 **`web/app.js` tem ~1.940 linhas** num arquivo só. Separar em módulos ES nativos (sem
  build): estado/API, tabela, preferências (etiquetas, stacks, termos), limpeza, exportação,
  LinkedIn, controle da busca. Sem mudança de comportamento; testes do painel intactos.
- 4.2 **`webapp.py` tem ~1.470 linhas**: `do_GET/do_POST/do_PUT` com cadeias de `if path ==`.
  Extrair uma tabela de rotas e módulos por assunto (preferências, exportação, limpeza, busca).
- 4.3 `fetching.py` (~710) e `sources/base.py` (~550): separar robots/bloqueio/ações de navegador
  e paginação/registro/fallback adaptativo (pendência antiga).
- 4.4 **Desempenho do classificador**: `_contains_term` monta a regex a cada chamada, para cada
  termo e cada vaga (a reaplicação do perfil roda isso milhares de vezes). Cachear os padrões
  compilados (`functools.lru_cache`) e medir antes/depois com a amostra real.
- 4.5 **Segurança do servidor local** (`127.0.0.1:8765`): validar o cabeçalho `Host`
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

1.4 → 1.1 → 1.2 → 4.4 → 4.5 → 1.3 → 3.1 → 2.3 → 4.2 → 4.1 → 2.2 → restante.

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

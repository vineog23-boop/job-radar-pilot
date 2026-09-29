# Scrapling independente para busca de vagas

## Objetivo

Instalar e configurar o repositório oficial `D4Vinci/Scrapling` como uma
ferramenta local e independente para descobrir vagas alinhadas ao perfil de
Vinícius. A ferramenta deve produzir dados estruturados que outra IA consiga
ler, deduplicar e filtrar sem depender do fluxo existente de vagas.

## Fora do escopo

- Não acessar ou alterar SQLite, Notion, RADAR, `pipeline-state.json` ou os
  arquivos de `Vagas Dev`.
- Não preencher ou enviar candidaturas.
- Não automatizar pesquisa autenticada no LinkedIn.
- Não contornar CAPTCHA, 2FA, bloqueios de acesso ou controles antiabuso.
- Não armazenar credenciais, cookies, tokens ou HTML integral nas saídas.

## Instalação

- Clonar o repositório oficial em versão fixada e registrar commit/tag usado.
- Usar Python 3.13 em ambiente virtual exclusivo do workspace.
- Instalar apenas os extras necessários para fetchers e páginas JavaScript.
- Instalar os navegadores exigidos pelo Scrapling no ambiente isolado.
- Manter dependências fixadas em arquivo reproduzível.
- Não instalar o pacote globalmente.

## Arquitetura

O workspace conterá o clone do Scrapling e um projeto separado chamado
`job-radar-pilot`. O projeto consumidor não modificará o código upstream.

Fluxo:

1. Carregar configuração de fontes, consultas e filtros.
2. Selecionar o fetcher adequado para a superfície.
3. Coletar cards e páginas de detalhe dentro dos limites configurados.
4. Normalizar os resultados no contrato canônico do piloto.
5. Validar campos e descartar registros sem identidade mínima.
6. Deduplicar o lote por identidade forte.
7. Gravar JSONL, CSV e relatório técnico da execução.

## Fontes

A configuração inicial abrangerá os bons portais já usados pelo usuário,
incluindo Gupy, Indeed, EstágioTrainee, Eureca, Programathor, Casa do Dev,
CIEE, Nube, Vagas.com, 99jobs, Cia de Talentos, Companhia de Estágios,
O Trainee, Vida de Trainee, Seja Trainee e InfoJobs, além de páginas públicas
oficiais de carreiras que adotem estruturas compatíveis.

Cada fonte terá configuração própria de URL inicial, paginação, limites,
extratores e necessidade de JavaScript ou autenticação. Fontes não validadas
não serão declaradas como cobertas.

## Autenticação e bloqueios

- Páginas públicas serão coletadas sem sessão autenticada.
- Quando uma fonte exigir login, o processo interromperá somente essa fonte e
  registrará um handoff para autenticação manual.
- CAPTCHA, 2FA, rate limit ou alerta de atividade encerram a tentativa daquela
  fonte sem bypass automático.
- Uma retomada após autenticação deve reutilizar somente o perfil local de
  navegador explicitamente destinado ao piloto, fora das saídas e do Git.

## Filtros iniciais

Os filtros refletirão a busca profissional do usuário:

- backend Java, Java 17 ou superior, Spring Boot, APIs REST, JPA/Hibernate,
  SQL, Maven, Docker e testes;
- estágio, júnior e oportunidades iniciais compatíveis;
- remoto no Brasil, híbrido elegível e localidades explicitamente configuradas;
- exclusão configurável de senioridade incompatível e vagas encerradas.

Os filtros servem para classificação e priorização. A coleta preservará os
dados factuais necessários para outra IA reavaliar a decisão.

## Contrato de saída

O arquivo principal será `output/vagas.jsonl`, em UTF-8, com um objeto JSON por
linha. `output/vagas.schema.json` descreverá o contrato e
`output/vagas.csv` oferecerá uma visão humana simplificada.

Campos mínimos por vaga:

- `source`, `source_job_id` e `canonical_url`;
- `title`, `company` e `description_summary`;
- `seniority`, `employment_type` e `technologies`;
- `location`, `workplace_model` e `remote_scope`;
- `published_at`, `observed_at` e `application_deadline` quando disponíveis;
- `requirements`, `eligibility_notes` e `evidence_snippets`;
- `match_labels`, `collection_status` e `content_hash`.

Campos ausentes serão `null` ou listas vazias conforme o schema; não serão
inventados. Evidências serão trechos factuais curtos, nunca páginas completas.

## Identidade e deduplicação

A prioridade de identidade será:

1. identificador inequívoco da plataforma;
2. URL oficial canônica sem parâmetros de rastreamento;
3. hash estável de empresa, título e localização apenas como fallback marcado.

Conflitos ou identidades fracas serão preservados no relatório como ambíguos,
sem fusão silenciosa.

## Relatório de execução

`output/relatorio-execucao.json` registrará:

- versão do coletor e do Scrapling;
- início, término e configuração não sensível;
- fontes tentadas, cobertas, vazias, parciais ou bloqueadas;
- páginas/cards observados, itens normalizados e duplicatas;
- paginação esgotada ou motivo de interrupção;
- erros sanitizados e handoffs manuais necessários.

## Tratamento de erros

Falhas serão isoladas por fonte. Uma fonte indisponível não invalida resultados
já validados de outras fontes. Retries terão limite e backoff. Mudanças de
layout resultarão em erro explícito de extração, sem produzir campos falsos.

## Testes e verificação

- Testes unitários dos normalizadores, canonicalização, filtros e deduplicação.
- Fixtures HTML locais para cada extrator, sem chamadas externas durante a suíte.
- Teste do schema sobre todas as linhas JSONL geradas.
- Smoke test controlado em poucas fontes públicas após os testes locais.
- Verificação de que nenhum segredo, cookie ou HTML integral aparece nas saídas.

## Critérios de aceite

- Instalação reproduzível em Python 3.13 e sem pacote global.
- Comando único documentado para executar o piloto.
- Pelo menos uma fonte pública validada ponta a ponta no smoke test.
- JSONL válido contra o schema, CSV consistente e relatório de cobertura gerado.
- Testes automatizados verdes.
- Nenhuma leitura ou escrita no fluxo existente de vagas.
- Limitações e fontes que exigem ação manual documentadas.

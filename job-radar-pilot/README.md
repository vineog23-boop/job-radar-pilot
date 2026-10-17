# Job Radar Pilot com Scrapling

Ferramenta local para encontrar vagas, conferir requisitos e acompanhar candidaturas,
com exportação da seleção para planilha, CSV ou relatório. O projeto usa o Scrapling
`v0.4.15`, instalado a partir do clone oficial fixado em `vendor/Scrapling`.

O fluxo de curadoria abaixo foi validado e aplicado no macOS em 17/10/2026.
Para instalar em outra máquina e conferir os requisitos, veja o
[guia de implantação e reversão](../docs/GUIA-IMPLANTACAO-CURADORIA.md).

## Uso rapido

**No Windows, sem terminal:** dê dois cliques em **`Radar de Vagas.cmd`** na raiz da pasta.
Na primeira vez ele instala o ambiente sozinho (precisa de Python 3.13 e Git
instalados) e depois abre o painel no navegador. Para ter um ícone na área de
trabalho, dê dois cliques uma única vez em **`Criar atalho na area de
trabalho.cmd`**. Para encerrar o Radar, feche a janela preta que fica aberta.

Pelo PowerShell, o equivalente é:

```powershell
.\abrir-interface.ps1
```

**No macOS:** abra **`Radar de Vagas.command`** na raiz do workspace. Ele usa
sua própria localização, prepara a venv quando ausente e abre o mesmo painel.
Instale antes Python **3.13** e Git; o Finder pode exigir permitir a abertura
nas configurações de segurança. Para executar no Terminal:

```bash
bash ./scripts/setup-mac.sh
./"Radar de Vagas.command"
```

O setup pode ser repetido sem apagar preferências ou vagas. Confere o Python,
a tag e o commit do Scrapling **0.4.15**, instala somente em
`job-radar-pilot/.venv` e mantém os launchers Windows. Para usar outro executável
Python 3.13, defina `JOBRADAR_PYTHON` com o caminho completo. Uma venv existente
com versão errada é recusada; recrie somente `.venv` após conferir o backup.
O launcher reutiliza somente o processo do painel iniciado com a mesma venv;
se a porta **8765** pertencer a outro processo, informa o conflito sem encerrá-lo.
O log fica em `~/Library/Application Support/JobRadar/logs/interface.log`
(ou em `LOCALAPPDATA/JobRadar/logs/interface.log` quando definido).
Feche com **Ctrl+C** no Terminal. Não copie o launcher isolado para outra pasta;
um atalho deve chamar o arquivo que permanece na raiz do workspace.

O painel abre em `http://127.0.0.1:8765`, mostra os resultados existentes e
permite:

- configurar termos de busca, estágio/júnior, remoto/híbrido/presencial,
  cidades, estados ou Brasil, **stacks** (pesam na aderência) e **termos de
  exclusão** (ex.: pleno, sênior, tech lead);
- salvar essas preferências somente neste computador;
- iniciar uma nova busca pelo botão **Buscar vagas agora**;
- filtrar por texto, portal e aderência, e ordenar por aderência ou por data de
  publicação;
- marcar cada vaga como **Salva**, **Aplicada**, **Entrevista**, **Oferta**,
  **Recusada** ou **Descartada**, com observação nas vagas acompanhadas;
- usar **Exportar resultados (N)** para baixar o recorte atual em planilha,
  relatório Markdown ou **CSV** (`;` e UTF-8 com BOM, abre direto no Excel).

**Salvar configurações** reclassifica as vagas já guardadas sem iniciar uma nova
busca. Faça backup antes de alterar o perfil de uma base importante. O servidor aceita
conexões somente deste computador; pressione `Ctrl+C` no terminal para encerrar.

Para executar somente pelo terminal:

```powershell
.\buscar-vagas.ps1
```

O comando pesquisa todas as fontes configuradas, valida o JSONL e informa onde
os resultados foram salvos. Para limitar a busca a uma fonte:

```powershell
.\buscar-vagas.ps1 -Fonte programathor
```

Para coletar fontes em paralelo, use de 1 a 4 workers. Cada fonte continua
sequencial internamente, inclusive suas consultas e limites de acesso. O padrão
permanece `1`:

```powershell
.\buscar-vagas.ps1 -Workers 3
```

Na CLI, a opção equivalente é `collect --workers 3`. A interface local também
aceita `--workers 3` ao iniciar o módulo `job_radar.webapp`. Os resultados são
sempre restaurados à ordem das fontes configuradas antes da classificação e da
deduplicação.

## Seu dia a dia com o Radar

Use as quatro áreas da navegação:

| Área | Para que serve |
|---|---|
| **Oportunidades** | Vagas ainda não acompanhadas, mais compatíveis com o perfil e com página de detalhes confirmada nos últimos sete dias. É uma seleção para avaliar; confirme o formulário no portal antes de se candidatar. |
| **A conferir** | Vagas ainda não acompanhadas dentro do foco, sem encerramento comprovado, mas com algum critério ou disponibilidade pendente. Não são recomendações confirmadas. |
| **Candidaturas** | Vagas salvas e demais etapas do acompanhamento, sem as descartadas. Inclui anúncios antigos ou encerrados. Abra o título para ler/editar a observação e ver a data de candidatura quando registrada. |
| **Configurações** | Perfil, portais, importação manual, verificação de links, limpeza e exportação automática. **Ver todos os resultados guardados** abre a visão ampliada para diagnóstico, inclusive fora do foco. |

Uma lista vazia em Oportunidades não significa que a base esteja vazia. Confira
**A conferir**, os filtros de texto/portal/período e a saúde das fontes em
Configurações. Os números das áreas medem seus conjuntos; filtros adicionais
podem reduzir a tabela. Salvar uma vaga a leva para Candidaturas; **Me candidatei**
registra uma ação sua, enquanto abrir o link apenas abre o anúncio.

**Buscar vagas agora** consulta os portais com o perfil salvo. A busca rápida de
TI e a seleção de portais ficam em Configurações. A busca diária Windows pode ser
agendada com `scripts\agendar-coleta.ps1 -Horario 08:00`; evite duplicar uma
rotina já atendida pelo Hermes.

Para levar a seleção consigo, escolha o formato junto à lista e clique em
**Exportar resultados (N)**. A exportação mantém os filtros, a área e a ordem
atual, incluindo resultados além das linhas já exibidas. Zero resultados gera
um arquivo sem vagas; se a base mudar durante a seleção, atualize antes de tentar
novamente. O painel avançado de exportação em Configurações continua permitindo
montar outra seleção, independente da tabela.

**Exportação automática** — ao fim das buscas que não usam `--no-export`, o Radar grava em
   **Documentos\Radar de Vagas**: `melhores-vagas-AAAA-MM-DD-HHMM.xlsx` (mais
   compatíveis + a revisar, sem descartadas, ordenadas pelo Score),
   `melhores-vagas-AAAA-MM-DD-HHMM.md`, `todas-de-ti-AAAA-MM-DD-HHMM.csv`
   e as cópias `ultima-busca.xlsx` / `ultima-busca.md`. Confira a data dos arquivos:
   uma seleção automática vazia pode manter a cópia anterior. Em **Configurações → Exportar vagas → Exportação automática** dá para
   desligar, trocar a pasta, **Abrir pasta** ou **Exportar agora**. Na linha de
   comando, `collect --no-export` pula a exportação de uma coleta. A integração
   Hermes usa essa opção; seus avisos no Telegram não atualizam essas planilhas.

No celular a tabela vira cartões (sem rolagem para os lados).

## Acompanhamento e exportação

O estado de cada vaga fica em `tracking.json`, na pasta de dados locais descrita
abaixo, fora do repositório e do funil canônico; a chave é a URL da vaga. Estados: **Salva**,
**Aplicada**, **Entrevista**, **Oferta**, **Recusada** e **Descartada**, cada um com a
data em que foi alcançado (`applied_at`, `interview_at`...) e uma nota curta que
não se perde ao mudar o estado. A faixa **Seu funil** acima da tabela conta as
vagas em cada etapa (clique para filtrar) e **Em processo** junta aplicadas,
entrevistas e ofertas. **Salvas** e **Em processo** abrem também registros antigos,
sem publicação ou encerrados, removendo os filtros de período e atividade; você
pode refinar a seleção depois. Salvar ou se candidatar a uma vaga protege seu
registro na coleta e na limpeza, mas não comprova disponibilidade. Acompanhar
em outra aba atualiza o painel sem perder o foco; o histórico continua na saída.
No botão **Exportar resultados (N)** junto à lista, e em **Configurações → Exportar vagas → Exportar a tabela**, CSV, relatório,
planilha e texto para IA respeitam todos os filtros ativos (incluindo remoto,
período, atividade e acompanhamento) e a ordem da tabela, inclusive além das
300 primeiras linhas. Uma tabela vazia gera um arquivo sem vagas. Se a saída
mudar após carregar a tabela, o download avisa para atualizar e tentar de novo.
Esses downloads usam somente as URLs e a versão carregadas, com limite de
20.000 vagas e corpo de 2 MiB. O CSV
traz aderência, acompanhamento, cargo, empresa, local, modalidade,
senioridade, tecnologias, data de publicação, fonte, URL e nota.

## Vigência: publicação, prazo e período

- **Publicada em** vem só do portal (campo estruturado ou texto "Publicada em"); a data de coleta (`observed_at`) nunca a substitui.
- **Vista pela 1ª vez** (`first_seen_at`, do histórico local) aparece só quando o portal não informa a publicação (Indeed, InfoJobs, Nube...). É informação, não data de publicação: ordenação e filtros de período continuam usando apenas `published_at`.
- **Prazo** (`application_deadline`) vem do `validThrough` da página oficial. Só a data vale até 23:59 de Brasília.
- O período pode ser **Últimos 30 dias** (também 7 e 15) ou **Qualquer data**. A navegação entre áreas começa sem restringir a publicação e preserva os refinamentos feitos em cada área durante a sessão. Vaga sem data de publicação fica fora das janelas e aparece em **Qualquer data**; nada é apagado. Prazo vencido afeta a **Situação**, não o período: consulte anúncios encerrados em Candidaturas ou na visão ampliada de Configurações. Oportunidades e A conferir excluem encerradas.
- **Período personalizado:** em "Personalizado…" informe data inicial e/ou final; os dois dias entram (horário de Brasília). Vaga sem data de publicação continua de fora.
- **Situação** (derivada, nunca gravada): *ativa* quando há prazo oficial em aberto com publicação ou detalhe confirmado nos últimos 7 dias; *listada na última busca* quando observada há até 7 dias; *encerrada* por prazo vencido ou HTTP 404/410 recente comprovado; *não comprovada* quando falta evidência. Listagem recente não confirma que o formulário ainda aceita candidatura. Oportunidades exige confirmação recente da página de detalhes, além da compatibilidade; registros antigos preservados continuam acessíveis em Candidaturas ou na visão ampliada.
- A coleta não abre a página de detalhe de vaga fora da janela ou com prazo vencido (`enrich_max_age_days`, padrão 30).
- **Gupy:** a API anônima (`gupy-api`) retornou 404 e está desativada; a fonte `gupy` usa a busca pública do portal, respeitando robots.txt, sem login. É cobertura parcial, sem garantia de disponibilidade.

## Limites de segurança

- Não acessa o SQLite de outros projetos, Notion, RADAR, `pipeline-state.json` nem a pasta
  `Vagas Dev`.
- Não preenche formulários nem envia candidaturas.
- LinkedIn: além da importação manual descrita abaixo, existe a fonte **opt-in**
  `linkedin` (guest API anônima, sem login), que consulta a busca pública de vagas
  com throttling alto e sem enriquecimento de detalhe. O robots.txt do LinkedIn
  não permite esse endpoint e os Termos proíbem coleta automatizada: a fonte fica
  desabilitada por padrão em volumes agressivos (máx. 2 páginas por combinação,
  intervalo ≥ 4 s) e deve ser usada só em baixo volume, por conta de quem
  habilitar. Para todo o resto do domínio, o bloqueio geral continua valendo.
- LinkedIn: o botão **Pesquisar no LinkedIn** gera, para cada termo do perfil, um
  link da busca oficial já filtrado por nível, modelo (remoto/híbrido/presencial),
  local e período (24 h, semana, mês). Você abre no seu navegador, na sua sessão.
  O Radar não lê a página nem acessa, captura ou armazena cookies/tokens.
- Para trazer as vagas do LinkedIn para a lista, use o **importador** do mesmo
  painel: cole links de vagas (`linkedin.com/jobs/view/...`), a URL da busca com a
  vaga aberta (`currentJobId`), o texto de um e-mail de alerta ou o CSV do export
  oficial de dados (Vagas salvas/Candidaturas). O Radar só interpreta o texto
  colado, classifica pelo seu perfil e junta à lista sem duplicar (fonte
  `linkedin`, rótulo `IMPORT:MANUAL`). Só com o link, o título vem do próprio
  endereço; colar o texto do alerta traz título, empresa e local.
- Não contorna CAPTCHA, 2FA, rate limit, login ou alerta de atividade.
- Quando uma fonte exige autenticação, ela termina com handoff manual.
- Não grava cookies, tokens, senhas, perfis do navegador ou HTML integral nas
  saídas.
- Os rótulos de aderência são sinais determinísticos, não fatos nem decisões de
  candidatura.
- O painel só responde ao próprio endereço (`127.0.0.1`/`localhost` na porta
  dele) e recusa pedidos de outros sites: um site malicioso aberto no navegador
  não consegue pausar/parar a busca, desfazer a limpeza nem ler suas vagas
  (proteção contra CSRF e DNS rebinding). Todo POST/PUT exige JSON.
- Os CSVs neutralizam células que o Excel trataria como fórmula (`=`, `+`, `-`,
  `@`): o texto ganha um `'` na frente. O `.xlsx` e o JSONL guardam o original.

`FIT:READY` significa somente **mais compatível no Radar local**. Ele não é o
estado `READY` canônico do funil/SQLite, não comprova vaga aberta e não autoriza
preenchimento, clique final ou envio de candidatura.

## Instalação

No PowerShell, a partir da raiz deste workspace:

```powershell
.\scripts\setup.ps1
```

No macOS, use `bash ./scripts/setup-mac.sh` na raiz.
O comando usa exclusivamente Python 3.13 em `job-radar-pilot/.venv`, instala o
clone oficial em modo editável com os fetchers e baixa os navegadores exigidos.
Nada é instalado no Python global.

## Conferir a configuração sem rede

```powershell
.\scripts\run-job-radar.ps1 --dry-run
```

O dry run valida `config/profile.yaml` e `config/sources.yaml`, lista as fontes
habilitadas com as opções efetivas de navegador/HTTP e não cria `FetchPolicy`
nem realiza requisições.

## Contexto do navegador e recursos por fonte

As coletas usam locale `pt-BR`, timezone `America/Sao_Paulo` e o cabeçalho HTTP
`Accept-Language: pt-BR,pt;q=0.9,en;q=0.6`. Esse contexto melhora a consistência
de idioma e formatação, mas **não é evidência geográfica**: ele não preenche
`default_country` nem transforma uma vaga remota em vaga no Brasil. Somente
Indeed e Casa do Dev preservam `default_country: BR` por evidência própria da
fonte.

Cada fonte pode declarar opções aditivas de navegador:

```yaml
browser:
  disable_resources: false
  blocked_domains: []
```

`disable_resources` e `blocked_domains` valem apenas para o request daquela
fonte. Domínios devem ser hostnames simples, sem esquema, porta, caminho ou
wildcard. A ausência de `browser` equivale aos valores acima; o bloqueio de
anúncios também permanece desligado (`block_ads=false`). Ative bloqueios somente
depois de comparar a coleta com e sem a opção e confirmar que status, motivo de
parada, páginas, URLs únicas, campos e completude não regrediram.

## Coletar

Uma fonte pública limitada:

```powershell
.\scripts\run-job-radar.ps1 --source programathor --output .\job-radar-pilot\output
```

Mais de uma fonte:

```powershell
.\scripts\run-job-radar.ps1 --source programathor --source indeed
```

Sem `--source`, todas as fontes habilitadas são tentadas sequencialmente.
Comece por lotes pequenos: layouts, termos e limites dos portais podem mudar.

## Saídas

- `output/vagas.jsonl`: formato principal; um objeto JSON por vaga.
- `output/vagas.csv`: visão humana reduzida.
- `output/relatorio-execucao.json`: versão, commit upstream, fontes, paginação,
  contagens, bloqueios, warnings e erros sanitizados.
- `output/vagas-descartadas-na-coleta.jsonl`: vagas que a limpeza automática da
  coleta descartou (fora do perfil, fora de TI, vencidas). Ficam guardadas para
  voltar à lista se você ampliar o perfil e usar **Salvar configurações**.
- `output/.radar-output.lock`: trava entre a coleta (inclusive a agendada) e o
  painel, para um não regravar a lista por cima do outro.

Na interface, **Baixar relatório** transforma em Markdown exatamente as vagas
visíveis pelos filtros atuais. O documento separa mais compatíveis, condicionais,
dados insuficientes, outra stack e fora do perfil; também registra os estados de cobertura de
cada portal. Se a saída local estiver corrompida, o download falha de forma
explícita em vez de gerar um relatório vazio. O arquivo é produzido localmente e
não é enviado para serviços externos.

Cada objeto JSONL contém origem, identidade, URL oficial, cargo, empresa,
descrição resumida, senioridade, tecnologias, localidade, modalidade, datas,
requisitos, evidências curtas, rótulos, status e hash de conteúdo. Campo factual
ausente é `null` ou lista vazia; o coletor não inventa valores.

Validar um arquivo:

```powershell
.\scripts\run-job-radar.ps1 validate-output .\job-radar-pilot\output\vagas.jsonl
```

## Códigos de saída

- `0`: dry run válido, JSONL válido ou coleta integralmente `SUCCESS`/`EMPTY`.
- `1`: JSONL inválido.
- `2`: argumento, fonte ou configuração inválida.
- `3`: coleta terminou honestamente com fonte parcial, bloqueada, autenticada ou
  em erro; consulte `relatorio-execucao.json`.
- `4`: busca interrompida pela pessoa (botão Parar no painel); o que já foi encontrado foi salvo.
- `5`: outra coleta (por exemplo, a agendada) já estava gravando a mesma pasta de
  saída; nada foi coletado. Tente de novo quando ela terminar.

`EMPTY` significa que a página declarou ausência de resultados. Se os seletores
esperados desaparecerem, o status é `ERROR/LAYOUT_CHANGED`, não vazio.
O coletor preserva o HTML integral recebido do Scrapling para o parsing. Os
marcadores de vazio são avaliados somente no texto visível, portanto conteúdo
em `script`, `style` ou elementos ocultos não declara `NO_RESULTS`.

## Paginação por fonte

- `next`: seletor do link da próxima página (programathor, casado-dev, seja-trainee).
- `declared_count`: total declarado pelo portal (99jobs, vagas-com).
- `single_page: true`: portal verificado com página 2 vazia/inexistente (otrainee, companhia-de-estagios, estagiotrainee, mytechjobs).
- Rolagem/botão em JavaScript virou observável: as ações de browser gravam
  `data-jr-load-complete` no HTML e o parser distingue lista completa
  (`EXHAUSTED`) de parada no teto (`SCROLL_LIMIT`, parcial por configuração).
  `browser.scroll_to_load` cobre eureca, cia-de-talentos, remotar e coodesh;
  `browser.click_to_load` cobre ciee e trampos ("Mostre-me mais vagas!");
  `browser.paginate_next` cobre os quadros de empresa da Gupy. O infojobs rola a
  listagem em JavaScript por ação dedicada e grava o mesmo marcador.

O fallback adaptativo só é aceito na primeira página, sem marcador de vazio e com
pelo menos duas vagas válidas (sem link de login/listagem e título com 8+ caracteres).
Da página 2 em diante, zero cards configurados encerra a listagem.

## Fontes adicionadas em setembro/2026

nerdin, mytechjobs (iMasters), empregos-com, trampos, remotar, coodesh e **geekhunter**
(o `robots.txt` do GeekHunter passou a liberar `/pt/vagas`; o filtro `?searchTerm=` recebe
os termos do perfil e a data vem de "Publicada há N horas"). Avaliadas e **não**
incluídas: TalenTI, eu.dev.br, ViUmaVaga, Super Estágios, Futura Estágios e Glassdoor
(o `robots.txt` bloqueia acesso automatizado); GitHub `backend-br/vagas`
(`robots.txt` nega `/issues`); Catho (login e proteção anti-bot); Revelo (404);
Quero Vagas Tech, VagasPraJr e EmpregosTech (domínio não resolve).

Avaliadas em 29/09/2026 e **não** incluídas:

- **Netvagas**: a listagem só carrega com JavaScript e o site recusa o navegador
  automatizado ("Não foi possível exibir esta página"). Contornar isso seria burlar a
  proteção, então não entra.
- **Abler** (`candidatos.abler.com.br/vagas`): cards sem link; cada vaga abre por clique em
  JavaScript, sem URL na listagem.
- **Quickin** e **Recrutei**: cada empresa tem o próprio quadro
  (`jobs.quickin.io/<empresa>/jobs`, `jobs.recrutei.com.br/<empresa>`); não há listagem
  geral. Os quadros são acessíveis, mas exigiriam uma lista de empresas.

### Quadros de empresa na Gupy (outubro/2026)

Quadros `<empresa>.gupy.io` têm markup e paginação próprios (por clique, sem URL por
página); o adaptador da Gupy ganhou a variante de quadro e a ação `paginate_next`.
Empresas mineradas do histórico de vagas relevantes e validadas ao vivo:
Compass UOL, Spread, Montreal, Quality Digital e SoftDesign (`gupy-compass`,
`gupy-spread`, `gupy-montreal`, `gupy-qualitydigital`, `gupy-softdesign`).
O quadro do Grupo Boticário saiu da lista: rendimento baixo para o perfil
(3 vagas úteis em 60 brutas, maioria não-técnica). Subdomínios InHire foram
testados e descartados: respondem 200 para qualquer nome (catch-all), sem prova
de quadro real.
- **APInfo**: só ~8 vagas por lista, sem paginação, busca por formulário e o `robots.txt`
  bloqueia explicitamente bots de IA.
- **Wellfound**: sem login só 2 vagas aparecem no HTML e são sêniores/internacionais.

## Rolagem, termos de busca e histórico

- `browser: {scroll_to_load: true}`: rola a página até a quantidade de cards estabilizar
  (eureca, cia-de-talentos, remotar, coodesh). O marcador `data-jr-load-complete`
  informa se a lista estabilizou de verdade; se a rolagem parar no teto configurado,
  a fonte termina em `SCROLL_LIMIT` (parcial por configuração). O nube foi removido
  do radar: rendimento baixo (25 vagas úteis de 1.821 brutas), era a fonte mais lenta
  da coleta e as vagas de "empresa confidencial" quebravam a deduplicação.
- `browser: {click_to_load: "<seletor>"}`: clica no botão "carregar mais" até ele sumir
  (ciee, trampos). Lista completa só quando o botão desaparece.
- `browser: {paginate_next: "<seletor>", paginate_max_pages: 6}`: para SPAs de quadro
  sem URL por página (Gupy empresa): clica em "próxima", acumula os cards de cada
  página e reescreve a listagem com todos antes do parse.
- `query_path: "/vagas-de-{query}"` ou `query_param: q`: fazem qualquer fonte receber a
  varredura de vários termos (vagas-com e infojobs já usam). O texto vira slug sem acento.
- Enriquecimento: vagas `CONDITIONAL`/`AMBIGUOUS` com tecnologia compatível têm a página de
  detalhe lida (HTTP estático, respeitando robots.txt e limites; ignora Indeed e fontes com
  login) e são reclassificadas; recebem `ENRICHED:DETAIL`. `collect --enrich-limit N`
  (padrão 120; `0` desliga). A fila vai das mais compatíveis para as duvidosas e, dentro de
  cada faixa, **vagas sem data de publicação primeiro** (sem data a vaga some dos filtros de
  período), com rodízio entre portais para que um portal grande não gaste o orçamento todo.
  Da página de detalhe saem data, prazo, empresa e **modalidade** (JSON-LD `datePosted`,
  `validThrough`, `jobLocationType: TELECOMMUTE`; `__NEXT_DATA__` da Gupy e do Remotar).
  O limite conta páginas distintas por portal: repetições da mesma URL nas buscas por
  termos são consultadas uma vez e recebem os mesmos detalhes, sem juntar IDs de vaga
  diferentes nos parâmetros da URL. Bloqueios também não são repetidos nessa rodada.
  `ENRICHED:DETAIL_AT:<ISO>` registra quando o texto foi obtido; `ENRICHED:DETAIL_COMPLETE`
  só aparece se o texto cabe inteiro, sem corte. O Hermes pode reaproveitar esses detalhes
  por até 24 horas; descrições antigas, sem data ou cortadas continuam sendo consultadas.
- Histórico local em `%LOCALAPPDATA%\JobRadar\history.json` (só chave da vaga e data da
  primeira observação). Da segunda coleta em diante, vagas inéditas ganham `STATUS:NEW` e
  o selo "Nova" no painel. `collect --no-history` desliga.
- Agendamento diário no Windows (Agendador de Tarefas):
  `schtasks /Create /SC DAILY /ST 08:00 /TN "JobRadar" /TR "powershell -NoProfile -File \"<pasta>\buscar-vagas.ps1\" -Workers 3"`

## Qualidade dos dados e avisos

- **Classificação:** texto que indica remoto no Brasil ("100% remota", "home
  office") prevalece sobre a cidade-sede do campo local; remoto no exterior
  (EUA, Canadá, Europa) não conta como Brasil. Júnior também reconhece `jr`,
  `nível 1`, `entry level`, `iniciante` e algarismo romano `I` ("Java I");
  estágio reconhece `trainee` e `aprendiz`. Faixas "Júnior/Pleno" e "Jr/Pl"
  ficam `CONDITIONAL` com `SENIORITY_UNCLEAR:range`.
- **Campos preenchidos com evidência:** `workplace_model` quando o texto indica
  uma única modalidade (`WORKPLACE_INFERRED:*`), `seniority` e `technologies`
  a partir do que o classificador detectou. Nada é inventado.
- **Data de publicação:** a fonte pode declarar o seletor opcional
  `published` (ex.: `"time::attr(datetime)"`). São aceitos ISO 8601,
  `dd/mm/aaaa` e datas relativas ("há 3 dias", "ontem", "3 days ago");
  sem evidência, `published_at` fica `null`.
- **Títulos:** o selo "Nova"/"Novo" e sufixos depois de `|` são removidos,
  exceto quando o sufixo informa senioridade ("Java | Júnior").
- **Duplicatas:** a mesma vaga vista mais de uma vez vira um registro só. O
  cargo é comparado sem "Remoto"/"home office"/"(Remoto)", com
  "Desenvolvedora"="Desenvolvedor(a)" e "Jr"="Júnior"; a empresa, sem "Ltda",
  "S.A." e "Brasil". O local precisa ser compatível (igual, ou um lado remoto ou
  sem local): duas cidades presenciais diferentes continuam separadas, e
  empresas diferentes nunca se juntam. Entre portais fica a versão do Gupy/ATS
  quando existir (`ALSO_SEEN_IN:<fonte>`, "também em …" no painel); no mesmo
  portal (republicação) fica o anúncio mais recente (`REPOSTED:<n>`,
  "Republicada N×"). Se você acompanha uma das URLs, é ela que fica.
- **Descrições limpas:** texto de `<script>`/`<style>` dentro do cartão, botões
  ("Quero essa vaga", "Salvar vaga"), caixas de compartilhar e o "Voltar" do
  Primeira Vaga Tech são removidos; títulos perdem códigos internos
  ("[Job-32006]", " - 386089", "(Cód. 123)").
- **Rendimento por portal:** o relatório guarda por portal `useful` (vagas que
  ficaram), `discarded` e `compatible`; em **Situação dos portais** o painel mostra
  esses números e avisa quando um portal rende pouco para o seu perfil.
- **Portal quebrado:** o histórico guarda as últimas 10 contagens por fonte.
  Com ao menos duas coletas anteriores, uma queda de mais de 50% gera
  `SOURCE_COUNT_DROP:atual<média` e uma coleta zerada gera
  `SOURCE_COUNT_ZERO`; o aviso vai para `warnings` do relatório, para o
  terminal e para os detalhes dos portais no painel. Coletas com erro ou
  bloqueio não entram na média.

## Opções de `config/sources.yaml`

| Chave | Efeito |
| --- | --- |
| `selectors.card/title/url` | Obrigatórios em fontes `generic`. |
| `selectors.company/location/summary/id` | Opcionais; ausência vira `null`. |
| `selectors.published` | Opcional; data de publicação (ver acima). |
| `selectors.next` | Link da próxima página. |
| `single_page` | Portal verificado sem página 2. |
| `browser.scroll_to_load` | Rola até a quantidade de cards estabilizar. |
| `browser.scroll_max_iterations` | Teto de rolagens quando `scroll_to_load` está ativo (padrão 40). |
| `browser.click_to_load` | Seletor do botão "carregar mais", clicado até sumir (ciee, trampos). |
| `browser.paginate_next` / `browser.paginate_max_pages` | Botão "próxima página" de SPA sem URL por página (quadros Gupy de empresa) e o teto de páginas (padrão 6). |
| `fixed_queries` | Não injeta os termos do perfil; sem `queries`, a fonte coleta só a `start_url` (quadros de empresa). |
| `browser.disable_resources`, `browser.blocked_domains` | Bloqueios opcionais por fonte. |
| `query_path` / `query_param` | Habilita a varredura de termos de busca. |
| `default_country` | País assumido para vagas remotas sem país explícito. |
| `adaptive` | Liga/desliga o fallback adaptativo (padrão `true`). |
| `default_company` | Empresa cadastrada explicitamente, usada somente quando ausente no cartão. |
| `default_workplace` | `REMOTE`, `HYBRID` ou `ONSITE` para portais de uma modalidade só (ex.: Remotar); só preenche modalidade desconhecida. |
| `selectors.company_from_title` | Regex (1 ou mais grupos; vale o primeiro preenchido) que tira a empresa do título em portais de programa ("Ingredion abre Programa de Estágio..."). |
| `selectors.company_from_url` | Regex com um grupo que tira a empresa da URL quando o cartão não traz (ex.: GeekHunter `/pt/<empresa>/jobs/`). |
| `fetch_details` | Permite enriquecimento e verificação automática de detalhes (padrão `true`). `false` mantém os links para visita manual. |
| `api.page_mode: single` | Uma requisição à URL exata, sem `page_param` obrigatório; `total_path` opcional confere a quantidade declarada. |
| `kind: json` + `api` | Portal com API JSON pública (Gupy, Primeira Vaga Tech). `api.items` (caminho da lista), `page_param`/`page_mode` (`offset`, `page0`, `page1` ou `single`)/`page_size`/`size_param`, `workplace_param`/`state_param` (filtros de modelo e estado vindos do perfil), `strip_levels` e `fields` (mapeamento `title`, `company`, `url` ou `url_template`, `published`...). Um portal novo vira só configuração. |
| `kind: rss` | Feed RSS público (Empregos Tech, 100% remoto). |

## Cobertura e integrações previstas

A configuração habilitada em `config/sources.yaml` define o que a busca consulta;
ter um adaptador ou um portal conhecido não garante cobertura completa. A pesquisa
pública de 06/10/2026 orientou a ativação das quatro listagens InHire, CI&T e
Greenhouse abaixo. As demais integrações mantêm os limites indicados:

| Portal | Escopo e limite |
|---|---|
| InHire | Páginas públicas **por empresa**, inicialmente Programmers e Bionexo; não existe cobertura global demonstrada de todos os clientes do ATS. SPA exige renderização. |
| CI&T | Somente a listagem oficial; detalhes com `?opportunity=` são restritos por robots.txt. Links de candidatura ficam para visita manual, sem enriquecimento nem confirmação automática desses detalhes. |
| Greenhouse | API pública de **um board cadastrado**, inicialmente AB InBev; cada empresa requer sua própria fonte. Nenhum acesso à API privada Harvest ou envio de candidatura. |
| 99Freelas | Projetos **freelance**, separados de vagas CLT/estágio; integração opcional pendente da categoria/contrato adequado. |
| Telegram | Pendente dos URLs de canais públicos indicados pelo usuário; sem descoberta inventada ou leitura de grupos privados. |
| LinkedIn | Fonte **opt-in** `linkedin`: guest API anônima da busca pública (sem login), com throttling alto e sem detalhe; fora dela, somente links oficiais de pesquisa e importação manual do conteúdo colado. |

## Notas externas (nota dos seus critérios no painel)

Opcional: se existir `output/notas.json`, o painel mostra a nota ao lado da aderência
(ex.: "87/100"), oferece a ordenação "Maior nota (seus critérios)" e, no detalhe, os eixos
da nota ou o motivo de a vaga não ter entrado no aviso. A automação diária do Hermes grava
esse arquivo, então o painel mostra **o mesmo número** do Telegram. O "Score X/100" do painel
continua sendo a pontuação do perfil do próprio Radar. Arquivo ausente ou ilegível é ignorado.

```json
{"versao": 1, "avaliador": "...", "notas": {
  "<canonical_url>": {"nota": 87, "trilha": "Java júnior", "eixos": {"nível": 25, "stack": 21},
                      "aderencia": {"atende": 5, "total": 6, "faltam": ["kubernetes"]},
                      "motivo": null},
  "<outra>": {"nota": null, "motivo": "nível acima de júnior"}}}
```

## Modalidade por região

Opcional, em `search-preferences.json` (o painel mostra a regra abaixo das localidades e a
preserva ao salvar; ainda não há campo para editá-la):

```json
"workplace_location_scopes": {
  "HYBRID": ["sp", "florianopolis-sc", "sao-jose-sc", "palhoca-sc", "biguacu-sc"],
  "ONSITE": ["sao-carlos-sp", "florianopolis-sc", "sao-jose-sc", "palhoca-sc", "biguacu-sc"]
}
```

Com ela, vaga híbrida ou presencial fora da região da sua modalidade fica "Fora do perfil"
(`REGION_MISMATCH:hybrid|onsite`, motivo "híbrido/presencial fora da região permitida"),
mesmo que a localidade esteja em `location_scopes` (ex.: "brasil" para aceitar remoto).
Remoto segue só `location_scopes`. Sem a regra, nada muda.

## Nome da empresa

Antes da classificação, o nome da empresa é limpo: saem emojis, hashtags e frases de
marketing ("Carreiras X", "Vagas na X", "X | Trabalhe Conosco", "Logo Programa de Estágio X
2027"). Se não sobrar nome (ex.: "VENHA SER #SANGUELARANJA"), ele vem do título
(`company_from_title`), da URL (`company_from_url`) ou do endereço do ATS
(`fcamara.gupy.io`, `jobs.lever.co/ciandt`, `jobs.quickin.io/sinqia`...). Isso também
melhora a remoção de duplicatas entre portais, que compara empresa + cargo.

## Fontes com API/feed (mais vagas, mais compatíveis)

`primeiravagatech`, `querovagastech` e `empregostec` leem dados estruturados (data,
empresa, modelo de trabalho, local) em vez de interpretar HTML. O `querovagastech`
(agregador, busca por termo no parâmetro `q`) entrega como URL o **link de candidatura
original**, muitas vezes o ATS da própria empresa (InHire, Gupy, site de carreiras). `gupy-api`
continua desativada após HTTP 404; o comportamento de sua configuração abaixo
se aplica somente se houver validação futura do endpoint. No Gupy API, cada
termo do perfil vira consultas por modelo (`remote`/`hybrid`/`on-site`) e por
estado das localidades escolhidas, com os níveis (júnior, pleno...) tirados do
termo porque o filtro de nível é feito pelo classificador. O limite é de 40
requisições por coleta e o ritmo respeita `min_interval_seconds`.

## Fallback adaptativo de cards

Cada fonte aceita `adaptive: true|false` em `config/sources.yaml`; a ausência da
chave equivale a `true`. O coletor tenta sempre o seletor configurado primeiro.
Depois de extrair ao menos uma vaga válida, ele pode memorizar uma impressão
estrutural sanitizada do card e usá-la para relocalizar cards quando somente o
layout mudar. `adaptive: false` desliga tanto a leitura quanto a atualização
dessa memória para a fonte.

A memória fica em `adaptive/adaptive.db` na pasta de dados locais do sistema
(ver **Dados locais e backup**), nunca no repositório. Ela contém apenas
estrutura necessária à relocalização: não grava
texto ou HTML da vaga, URL/`href` da vaga, cookie, token ou segredo.

Uma relocalização não é tratada como cobertura integral: a fonte retorna no
máximo `PARTIAL`, registra o warning `SELECTOR_RELOCATED:card` no relatório e
marca as vagas com `EXTRACTION:ADAPTIVE`. A CLI exibe o warning em uma linha
separada, sem alterar a linha de progresso consumida pela interface.

## Sugerir seletores sem alterar a configuração

O diagnóstico abaixo busca uma página uma única vez e imprime YAML para revisão
humana. Ele não edita `config/sources.yaml` nem consulta ou atualiza o SQLite
adaptativo:

```powershell
.\scripts\run-job-radar.ps1 suggest-selectors programathor --text "Desenvolvedor Java Junior"
```

Também é aceita uma URL HTTPS da mesma origem de uma fonte configurada. Nesse
caso, o comando preserva o tipo e a política de coleta da fonte, mas usa a URL
somente durante o diagnóstico:

```powershell
.\scripts\run-job-radar.ps1 suggest-selectors "https://programathor.com.br/jobs-java?q=backend" --text "Desenvolvedor Java Junior"
```

URLs com credenciais, HTTP, `localhost`, IPs privados, loopback ou link-local
são recusadas antes da coleta. O host de uma URL crua precisa resolver somente
endereços globais, e mudanças de origem na resposta também invalidam o
diagnóstico. A saída informa `card`, `title`, `url`, cards encontrados e a
validação dos campos; revise o YAML antes de aplicá-lo manualmente.

## Dados locais e backup

A raiz compartilhada de preferências, histórico, acompanhamento, perfis de busca,
sessões de navegador e cache adaptativo fica fora do repositório:

| Sistema | Pasta padrão |
|---|---|
| Windows | `%LOCALAPPDATA%\JobRadar` (fallback `~/AppData/Local/JobRadar`) |
| macOS | `~/Library/Application Support/JobRadar` |
| Linux | `$XDG_DATA_HOME/job-radar` ou `~/.local/share/job-radar` |

Um `LOCALAPPDATA` explícito tem prioridade em qualquer sistema, preservando
instalações e testes antigos. Caminhos explícitos passados às APIs continuam
valendo. O setup não migra nem remove automaticamente dados da antiga pasta
`~/AppData/Local/JobRadar` no Mac: com o painel fechado, faça backup e copie o
conteúdo para a pasta nativa caso já tenha usado a instalação antiga.

Para backup, feche o painel e as coletas e copie a pasta de dados locais,
`job-radar-pilot/output/` e a pasta de exportações. `tracking.json` guarda estados
por URL; `history.json` guarda primeiras observações e histórico de contagens;
`profiles/*.json` são perfis de busca nomeados e `profiles/<fonte>/` são sessões de
navegador que podem conter cookies. `auto-export.json`, `cleanup-rules.json` e
`custom-stacks.json` ficam ao lado das preferências. Trate o backup dos perfis de
navegador como privado. A exportação padrão fica em `~/Documents/Radar de Vagas`
(Documentos no Windows); `JOB_RADAR_EXPORT_DIR` altera esse padrão e a pasta
escolhida no painel continua sendo respeitada. **Abrir pasta** usa Finder no
macOS, Explorador no Windows e `xdg-open` no Linux, sem comandos de shell.
Nenhum desses arquivos deve entrar no Git.

## Preferências de busca

Use **Configurar busca** na interface. Os valores ficam em
`search-preferences.json` na pasta de dados locais do sistema, fora do
repositório. As consultas personalizadas são aplicadas às fontes que oferecem busca por texto;
nível, modalidade e localidade também participam da classificação das vagas.

Uma modalidade desconhecida nunca é apresentada como correspondência
confirmada. Artigos editoriais permanecem para revisão e não são promovidos
automaticamente a vaga aplicável sem evidência suficiente.

## Autenticação manual

`AUTH_REQUIRED`, `LOGIN_REQUIRED`, `TWO_FACTOR`, `CAPTCHA` e
`ACTIVITY_ALERT` não são burlados. Para preparar uma sessão local de um portal:

```powershell
.\scripts\run-job-radar.ps1 auth CODIGO_DA_FONTE
```

Conclua senha, CAPTCHA ou 2FA diretamente na janela do navegador e feche-a
quando o comando orientar. O piloto não solicita nem grava senhas. Cookies da
sessão ficam em `profiles/<fonte>/` na pasta de dados locais do sistema, fora do repositório e das
saídas. Salvar o perfil não prova que o login terminou: a confirmação acontece
na coleta seguinte. A descoberta atual usa as páginas públicas; login só deve
ser usado quando um portal realmente o exigir.

## Prompt curto para outra IA

> Leia `vagas.jsonl` linha por linha. Filtre oportunidades de estágio ou júnior
> em backend Java/Spring, compatíveis com trabalho no Brasil e com minha
> localidade. Trate `match_labels` apenas como sinais para revisão; confirme
> requisitos, senioridade, localidade e abertura usando os campos factuais e a
> `canonical_url`. Separe vagas aplicáveis, condicionais e ambíguas sem inventar
> informações ausentes.

## Use com o seu perfil (qualquer stack, qualquer nível)

O Radar não é só para Java júnior. No painel, em **Configurar busca**:

1. **Stacks de interesse** — 25 stacks prontas (Java, Python, Node/TypeScript, Front-end, Full stack, .NET, PHP, Go, Kotlin, Ruby, Rust, C/C++/Embarcados, Mobile, Dados, IA/ML, DevOps, QA, Segurança, Suporte/Infra, Salesforce, SAP/ABAP, Low-code/RPA, Games, Produto, UX/UI…). Marque e clique em *Preencher sugestões*: o painel monta as tecnologias (que pontuam a vaga) e os termos de busca (enviados aos portais). *Somar ao que já está preenchido* acrescenta em vez de substituir.
   **✨ Gerar termos da área** (abaixo de *Termos de busca*) monta os termos sozinho: para cada stack marcada combina a tecnologia principal, os cargos que recrutadores mais usam (desenvolvedor, programador, dev, backend; analista de dados, analista de suporte, consultor SAP…) e os sinônimos de nível (estágio/estagiário, júnior/jr, sênior/sr), mais termos gerais da área ("estágio TI", "desenvolvedor júnior"). Os recomendados vêm marcados (★, alternando entre as áreas por prioridade); você marca/desmarca e escolhe *Usar selecionados* ou *Somar aos atuais*. Sem stack marcada, ele deduz pelas tecnologias principais preenchidas. O limite subiu para **20 termos**, e o painel mostra quantas consultas isso gera (termos × portais com busca por texto): mais termos trazem mais vagas, mas a busca demora mais.
2. **+ Criar stack** — não achou a sua? Dê um nome, liste as tecnologias e (opcional) os termos de busca. A stack fica salva em `custom-stacks.json` (ao lado das preferências), aparece com borda tracejada e pode ser excluída no ×.
3. **Nível** — estágio, júnior, pleno e/ou sênior. Vagas de outro nível ficam fora do perfil; um nível marcado nunca é tratado como exclusão (quem escolhe sênior também aceita cargos de liderança).
4. **Modelo de trabalho e localidades** — remoto/híbrido/presencial; use "Cidade UF", um estado, `brasil` ou `remoto-brasil`.
5. **Tecnologias** — campo de etiquetas (Enter ou vírgula adiciona, × remove, colar uma lista adiciona várias). Abaixo aparecem as tecnologias que mais se repetem nas suas vagas de TI e ainda não estão no perfil: um clique adiciona.
6. **Salvar como perfil** — guarde vários perfis (ex.: "Python pleno remoto", "Java júnior SP") e alterne entre eles no seletor; o perfil ativo é o que a próxima coleta usa.

Salvar ou ativar um perfil reaplica a classificação às vagas existentes sem
nova consulta aos portais. Tecnologias antigas explícitas no formulário não
herdam a stack do YAML: escolher Python com tecnologias preenchidas usa esse
perfil. Ao selecionar um nível, exclusões contraditórias daquele nível são
normalizadas; níveis fora da seleção continuam excluídos. Se a coleta, uma
verificação ou outra alteração da saída estiver em andamento, a operação recusa
com aviso de ocupação (HTTP 409) e preserva o perfil anterior. `STATUS:NEW`,
origem, evidências de disponibilidade e acompanhamento não viram classificação.

### Foco de programação e exceções de estágio

Em **Configurações → Configurar busca**, a opção **Somente desenvolvimento de
software** ativa a curadoria por função. Suporte, infraestrutura, dados/BI,
QA/testes e segurança não entram como desenvolvimento apenas por mencionar Java
ou SQL. Cargo genérico sem função confirmada fica para conferir.

Para um foco Java/Spring, escolha **Java** e **Spring Boot** nas tecnologias
principais. Elas representam o núcleo aceito; não é obrigatório que a vaga cite
as duas ao mesmo tempo. SQL, ferramentas de apoio e a expressão genérica “full
stack” não devem ampliar esse núcleo por acidente.

Com o foco de desenvolvimento ativado, marque, se desejar, **Estágios em
Inteligência Artificial** e **Estágios full stack**. São exceções explícitas ao
núcleo de tecnologia somente para anúncios identificados como estágio; não
ampliam a seleção para júnior, pleno, sênior, trainee ou aprendiz. Continuam
valendo os níveis escolhidos, local, modalidade e exclusões do perfil. Uma
menção incidental a IA no corpo de um estágio genérico não prova a exceção.
As opções vêm desligadas quando não foram configuradas; salvar é uma ação sua
e não altera `config/profile.yaml`.

### Palavras-chave e filtros finos

Tudo opcional; cada item vira um rótulo na vaga e aparece no detalhe e no motivo da exportação:

| Campo | O que faz |
|---|---|
| **Obrigatórias** | A vaga precisa citar pelo menos uma (`KEYWORD_MATCH`); sem nenhuma, fica fora do perfil (`KEYWORD_MISSING`). |
| **Diferenciais** | Nunca excluem: +5 no score por diferencial (até +10) e desempate no ranking (`BONUS_MATCH`). |
| **Proibidas na vaga** | Em qualquer parte, cargo ou descrição, tiram a vaga do perfil (`KEYWORD_BLOCKED`). |
| **Proibidas no cargo** | Só no título (`TITLE_EXCLUDED`); termos de nível continuam como `SENIORITY_MISMATCH`. |
| **Empresas a evitar / favoritas** | Evitar exclui (`COMPANY_EXCLUDED`); favorita soma +10 no score (`COMPANY_FAVORITE`). Sugestões de favoritas vêm das empresas com mais vagas compatíveis. |
| **Tipo de contrato** | CLT, PJ, Freelance/temporário. Só exclui quando a vaga diz explicitamente um contrato não aceito; "CLT ou PJ" passa se um deles for aceito; vaga que não fala de contrato nunca é excluída. |
| **Idioma** | "Esconder vagas que exigem inglês avançado ou fluente". Quando o inglês aparece como diferencial/desejável, a vaga continua (`LANGUAGE:english_plus`). |

**Ver impacto** mostra, sem salvar, quantas vagas da lista ficariam "Mais compatíveis", "A revisar", "de outra stack" e "Fora do perfil" com as configurações da tela. **Salvar configurações** sempre recalcula a aderência da lista atual, sem consultar os portais; a limpeza é uma ação separada. Faça backup antes dessa reaplicação. As vagas que a coleta tinha descartado também são reavaliadas: se o perfil novo for mais amplo, as que agora passam pelas regras de limpeza voltam para a lista. Se uma coleta ou verificação estiver gravando a saída, o painel informa ocupação e pede nova tentativa, preservando o perfil anterior.

### Faixas de aderência

| Faixa no painel | Rótulo | Quando |
|---|---|---|
| **Mais compatível** | `FIT:READY` | Cita a sua stack e confirma nível, local e modelo de trabalho. |
| **A revisar** | `FIT:CONDITIONAL` | Cita a sua stack, mas falta confirmar nível, local ou modelo. |
| **Dados insuficientes** | `FIT:AMBIGUOUS` | Vaga de TI sem stack nenhuma no texto (ex.: "Desenvolvedor Back-end Júnior" sem descrição). Boa candidata a abrir e ler. |
| **Outra stack** | `FIT:OTHER_STACK` | Vaga de TI que cita outra stack (Python, Node, .NET, PHP, React…) e nenhuma tecnologia sua; o motivo mostra qual (`OTHER_STACK:python`). Filtro próprio "Outra stack". |
| **Fora do perfil** | `FIT:EXCLUDE` | Nível, local, modelo, contrato, empresa ou palavra proibida não batem. |

"Backend", "front-end", "full stack", "API REST" e "mobile" descrevem a função, não a stack: só contam como sua tecnologia principal quando o perfil não tem nenhuma tecnologia específica. Assim, "Backend Python Júnior" não vira "Mais compatível" para um perfil Java.

As tecnologias aceitam apelidos nos dois sentidos: `springboot`/`spring-boot`, `node`/`nodejs`/`node.js`, `js`/`javascript`, `k8s`/`kubernetes`, `postgres`/`postgresql`, `csharp`/`c sharp`/`c#`, `dotnet`/`.net`, `go`/`golang`. Termos curtos têm regras próprias para não confundir: `go` não casa com "go-live" nem com a sigla de Goiás, `js` não casa com "JSP" nem "Node.js", `r` não casa com "R$".

### Pausar ou parar a busca

Durante uma busca aparecem **⏸ Pausar busca** e **■ Parar e salvar**. Pausar congela a coleta depois da página atual (nenhuma requisição nova sai) e **▶ Retomar** continua de onde parou. Parar termina a consulta em andamento, não começa outra e grava o que já foi encontrado: portais que nem começaram e os interrompidos no meio mantêm as vagas da coleta anterior. Por baixo, o painel escreve `pause`/`stop` em `output/.radar-control`, e `job-radar collect --control-file <arquivo>` lê esse arquivo (código de saída 4 = parada pela pessoa).
### Exclusões e limpeza

Em **Configurar busca**, a seção **Exclusões** guarda os *termos que você nunca quer ver*. Vagas com esses termos no cargo ficam fora do perfil. Com foco em desenvolvimento, um nível superior explícito não é anulado pela presença simultânea de “júnior”.

Todo o resto da limpeza fica em **Configurações → Limpeza**:

1. **Regras automáticas** — caixas para *fora da área de tecnologia*, *fora do meu perfil*, *inscrições encerradas* e, opcionalmente, *Fora das tecnologias principais e dos estágios que considero*, mais idade máxima. A opção de outra stack (`other_stack`) vem desligada: esconder da curadoria não é o mesmo que remover da base. Ative-a somente se quiser descartar essas vagas nas próximas coletas. As regras são gravadas ao mudar (`cleanup-rules.json`); `--keep-all` ignora as regras e `--max-age-days N` sobrepõe a idade. Confira a prévia antes de limpar uma base existente.
2. **Limpar o que já está salvo** — ao abrir o menu, a prévia já mostra quantas vagas seriam removidas, por motivo, com exemplos (título, empresa, portal). Há uma opção para remover também as vagas que você marcou como *descartadas*.
3. **Desfazer** — antes de limpar, as vagas removidas vão para `vagas.antes-da-limpeza.jsonl`; o botão *Desfazer última limpeza* devolve todas (a cópia vale para a última limpeza).

Vagas que você marcou como salva ou aplicada nunca são apagadas. Se o arquivo de acompanhamento (`tracking.json`) estiver ilegível ou contiver alguma entrada inválida (URL, estado ou valores que não são texto), a limpeza do painel recusa e a coleta grava tudo sem descartar, para não apagar justamente as vagas que você salvou. A coleta preserva também vagas acompanhadas que não reapareceram e as vagas anteriores dos portais bloqueados ou incompletos, mantendo a data em que foram observadas. Se o acompanhamento ficar ilegível durante a busca, todas as vagas anteriores são preservadas. Gravações simultâneas do acompanhamento mantêm as URLs, notas e datas de cada etapa. Se o `vagas.jsonl` tiver uma linha estragada, coletar, limpar, desfazer e reaplicar recusam e avisam em vez de regravar o arquivo sem ela.
## Rotina diária e portais de tecnologia

- `collect --tech-only` consulta apenas portais marcados com `tech_focus: true` em `config/sources.yaml`.
- Portais com `fixed_queries: true` (GeekHunter, Quickin) mantêm suas próprias consultas e não são sobrescritos pelos termos salvos no perfil.
- Buscas parciais (`--source`/`--tech-only`) preservam as vagas dos demais portais no `vagas.jsonl`.
- Vagas sem relação com TI recebem `RELEVANCE:OFF_TOPIC` e ficam ocultas no painel (filtro "Fora de TI").
- Agendar coleta diária com aviso de vagas novas: `scripts\agendar-coleta.ps1 -Horario 08:00` (remover com `-Remover`).
- Detalhes da revisão: `docs/REVISAO-2026-09-29.md`.

### Como o Radar roda (três formas, mesma pasta de saída)

| Forma | Onde | Quando | O que faz |
|---|---|---|---|
| Atalho "Radar de Vagas" (`.cmd`/`.lnk`) | Windows | ao abrir | painel em `127.0.0.1:8765`; busca pelo botão |
| `Radar de Vagas.command` | macOS | ao abrir | o mesmo painel |
| Automação Hermes (cron, fora deste repositório) | macOS | todo dia 08:30 | `collect --workers 3 --enrich-limit 250 --no-export` + `verify-links --limit 150` na pasta `output/` do painel; depois aplica os critérios pessoais e envia 2 a 4 vagas ao Telegram |

As três usam a mesma `output/` e o mesmo histórico, então o painel mostra exatamente a
coleta que gerou o aviso do Telegram. A trava `output/.radar-output.lock` impede coleta e
painel de regravar ao mesmo tempo: se o painel estiver ocupado, a automação sai com o
código 5 e o aviso usa a última coleta válida. Vagas marcadas pelo Telegram ("apliquei
na 2") vão para o mesmo `tracking.json` do painel. Detalhes: `docs/REVISAO-2026-10-10.md`.
## Medir o classificador (`avaliar`)

Para saber se uma mudança no classificador melhorou ou piorou, sem acessar portal nenhum:

```powershell
.\scripts\run-job-radar.ps1 avaliar                                   # amostra real em tests/fixtures
.\scripts\run-job-radar.ps1 avaliar --salvar antes.json               # guarda o resultado
.\scripts\run-job-radar.ps1 avaliar --base antes.json                 # antes x depois
.\scripts\run-job-radar.ps1 avaliar --preferencias "$env:LOCALAPPDATA\JobRadar\search-preferences.json"
```

Mostra quantas vagas caem em cada faixa, por portal, os motivos mais comuns e quais vagas mudaram de faixa. Sem gabarito, isso mede **mudança**, não **acerto**. Para medir acerto, abra `tests/fixtures/gabarito-amostra.csv` (60 vagas da amostra) e preencha a coluna `esperado` com a faixa que **você** daria: `READY`, `CONDITIONAL`, `AMBIGUOUS`, `OTHER_STACK`, `EXCLUDE` ou `OFF_TOPIC`. O arquivo não mostra a faixa do classificador de propósito, para não influenciar a sua resposta. Com linhas preenchidas, o `avaliar` mostra a taxa de acerto e as confusões. A base de antes das mudanças de 01/10/2026 está em `tests/fixtures/avaliacao-base-antes-p1.json`.

## Desenvolvimento e testes

```powershell
$env:PYTHONPATH = (Resolve-Path .\job-radar-pilot\src).Path
.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot\tests -v
```

Definir o `PYTHONPATH` dessa forma garante que os testes usem o código deste
workspace, mesmo quando a instalação editável da `.venv` ainda aponta para
outro checkout. Os launchers `run-job-radar.ps1` e `abrir-interface.ps1` fazem
essa priorização automaticamente.

No Linux/macOS: `PYTHONPATH=job-radar-pilot/src job-radar-pilot/.venv/bin/python -m pytest job-radar-pilot/tests -q -p no:cacheprovider`.
O GitHub Actions (`.github/workflows/tests.yml`) roda a suíte completa a cada
push com Python 3.13, Scrapling `v0.4.15` e Chromium do Playwright.

Pastas `job-radar-pilot/.tmp-*` e `debug.log` são descartáveis (ignoradas pelo
Git) e podem ser apagadas a qualquer momento.

Os testes de extratores usam fixtures locais sanitizadas. Apenas o smoke test
explicitamente executado acessa uma fonte pública.

Os seletores das 22 fontes habilitadas foram validados ao vivo em setembro de
2026 e têm testes determinísticos por comportamento. A fonte Vida de Trainee
fica desabilitada porque o arquivo observado estava parado em 2024. Portais
externos continuam sujeitos a mudanças de layout, bloqueios e paginação não
observável; nesses casos, o coletor retorna estado parcial ou erro explícito em
vez de declarar cobertura completa.

## Exportação atual e seleção avançada

Use primeiro **Exportar resultados (N)** junto à lista para preservar a seleção
atual e sua ordem. Para montar outro recorte, **Configurações → Exportar vagas**
abre um painel independente com atalhos e filtros e baixa um
`.xlsx` no formato de acompanhamento (Empresa, Cargo, Nível, Modalidade,
Localização, Score, Status, Publicada em, Link da Vaga, Tecnologias, Portal,
Observações), com cabeçalho fixo, filtros automáticos, links clicáveis e cores por
score, modalidade e status. Uma segunda aba registra os filtros usados e como o
Score é calculado. Atalhos: **Melhores para mim** (só `FIT:READY`, score ≥ 70,
últimos 30 dias), **Compatíveis + a revisar**, **Novas desde a última coleta** e
**Todas de TI**. Dá para refinar por score mínimo, período, nível, modelo,
portal e acompanhamento; o painel mostra quantas vagas serão exportadas. Vagas
fora da área de tecnologia nunca entram. Os filtros deste painel são
independentes dos filtros da tabela; seus downloads mantêm as rotas GET
existentes. As seleções **Melhores para mim** e **Compatíveis + a revisar**, assim
como a exportação automática das melhores vagas, excluem vagas encerradas mesmo
sem limite de período. O Score (0-100) soma 20 pontos por
critério atendido (tecnologia, nível, local, modelo), +10 se `FIT:READY` e até
+10 pela recência, usando dias fracionários; datas futuras não recebem esse
bônus nem entram em janelas de recência. Os mesmos filtros valem para CSV e
relatório (`.md`).

## Verificar se os links ainda estão no ar (`verify-links`)

A data da coleta não prova que a vaga ainda está disponível agora: um
agregador pode manter uma vaga removida na listagem, ou a vaga pode ter saído
do ar minutos depois da coleta. `job-radar verify-links` refaz o fetch do
link de cada vaga READY/CONDITIONAL salva, agora, e grava o resultado como
rótulo (`LINK:LIVE`, `LINK:DEAD` ou `LINK:UNKNOWN`, mais
`LINK_CHECKED_AT:<data>` e `LINK_CHECK_METHOD:JOB_DETAIL_V2`), preservando a data da
observação e o acompanhamento:

```
python -m job_radar.cli verify-links            # so READY/CONDITIONAL, ate 80 por chamada
python -m job_radar.cli verify-links --limit 0  # sem limite
python -m job_radar.cli verify-links --all      # verifica todas as vagas, nao so as melhores
```

`LINK:DEAD` é reconhecido por mensagens típicas de página removida ("vaga não
encontrada", "vaga expirada", "job no longer available" etc. — mesmo quando o
portal responde HTTP 200, um "soft 404"). Fontes que bloqueiam scraping
direto (ex.: `indeed`), desativadas ou autenticadas ficam `LINK:UNKNOWN` sem gastar requisição.
HTTP 404/410 só encerra a vaga quando recebido de uma consulta autorizada pelo
FetchPolicy. `LINK:LIVE` exige detalhes e candidatura, ou metadados JobPosting,
com o título correspondente quando conhecido. Página institucional, login,
CAPTCHA e redirecionamento à página inicial não comprovam disponibilidade.

No painel, **Verificar disponibilidade** consulta até 80 vagas compatíveis,
priorizando o Score, e mostra progresso e contagens. Busca, limpeza, importação
e reaplicação aguardam a verificação terminar. Evidência de link vale por sete
dias; LIVE antigo, futuro ou legado sem o marcador de método não confirma a
vaga. Prazo vencido prevalece mesmo sobre LIVE. Uma nova coleta preserva a
verificação anterior da mesma URL sem renovar sua data.

Em **Situação da vaga → Disponibilidade confirmada**, a tabela mostra somente
páginas de detalhes confirmadas nos últimos sete dias pelo método atual de verificação.
Listagem recente, prazo futuro, verificação antiga ou inconclusiva não bastam para
esse filtro. Ao expandir a vaga, aparece a data e hora da confirmação. A escolha é
lembrada no navegador e vale também para a exportação exata da tabela.

Os scripts
em `scripts/exportar_verificadas.py` (XLSX) e `scripts/exportar_csv_verificadas.py`
(CSV) exportam só as vagas com `LINK:LIVE`.

## Organização do painel

- **Navegação:** Oportunidades, A conferir, Candidaturas e Configurações.
  Perfil, fontes e manutenção ficam em Configurações; a ação de exportar a
  seleção fica junto à lista.
- **Configurar busca:** linha "Você procura: …" com o resumo do perfil, seções
  numeradas na ordem de preenchimento e **Filtros avançados (opcional)** recolhidos
  com contador (abrem sozinhos quando algum está em uso).
- **Contagens:** os números das áreas resumem seus conjuntos; os filtros
  adicionais podem deixar menos linhas na tabela. A visão de todos os resultados
  guardados fica em Configurações.
- **Detalhes por vaga:** clique no cargo para abrir descrição, score, critérios
  atendidos (tecnologia, nível, local, modelo), alertas e tecnologias.
- **Contexto:** o navegador lembra a área; refinamentos de cada área são mantidos
  durante a sessão. **Limpar filtros** permite remover restrições adicionais.
- **Atalhos:** `/` foca a busca; `Esc` fecha painéis e limpa a busca.
- **Exportar resultados (N):** planilha `.xlsx`, CSV ou relatório com o recorte
  atual. Configurações mantém a seleção avançada e a opção **Texto para IA**.

### Stack principal e aplicação do perfil

Em **Configurar busca**, defina a **Stack principal** (por exemplo, Java) e as
**Tecnologias complementares** (Spring Boot, SQL, Docker). Para aparecer como
"Mais compatível", a vaga precisa citar ao menos uma principal no texto ou nas
tecnologias informadas pelo portal, exceto quando se enquadra em uma trilha de
estágio explicitamente aceita no foco de desenvolvimento. Várias principais são alternativas: Java e
Python aceitam evidência de qualquer uma. Sem principal explícita, as preferências
antigas mantêm a classificação anterior. Uma vaga sem evidência recebe o motivo
"stack principal não confirmada na vaga"; os filtros de nível, local e exclusões
continuam valendo.

Os presets preenchem escolhas de principais; sugestões acrescentam termos de busca
sem apagar os já personalizados (até o limite de 20 termos). Salvar configurações,
salvar um perfil ou ativá-lo reaplica o perfil às vagas da lista e atualiza os
resultados imediatamente. Editar configurações atualiza também o perfil ativo.
Durante coleta ou verificação de links, a aplicação é recusada até a operação
terminar. Falhas na aplicação restauram preferências, perfis e resultados
anteriores; acompanhamento, notas, datas de observação e verificação dos links são
preservados.

### Novas listagens públicas por empresa

O seletor de portais inclui **InHire — Programmers**, **InHire — Bionexo**,
**CI&T** e **Greenhouse — AB InBev**. Cada entrada cobre a listagem pública da
empresa indicada, sem prometer cobertura de todo o ATS. O radar aguarda os
cartões renderizados do InHire e consulta a API pública Job Board da Greenhouse
uma vez, com `content=true`, sem parâmetros de paginação não documentados.

A CI&T oferece vagas globais; o idioma da página não determina o país da vaga.
Os links de candidatura continuam acessíveis manualmente. A configuração
`fetch_details: false` impede tanto enriquecimento como verificação automática
de detalhes da CI&T, respeitando a restrição de robots. Também é usada nas
novas fontes InHire (detalhes SPA) e Greenhouse (descrição já incluída na API).
`default_company` preenche somente empresas ausentes no cartão, sem substituir
uma empresa informada pela fonte.

Datas de publicação ausentes continuam desconhecidas. Na Greenhouse, a publicação
vem de `first_published`, não de `updated_at`. Um total declarado incompatível
com os itens recebidos gera coleta parcial; estrutura ausente ou shell SPA sem
cartões gera erro. Novos controles de carregar mais nas listagens pesquisadas
sinalizam cobertura parcial até que a paginação seja validada.

99Freelas continua separado como projetos freelance; Telegram depende de canais
públicos informados pelo usuário. LinkedIn mantém pesquisa e importação manuais.

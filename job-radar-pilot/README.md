# Job Radar Pilot com Scrapling

Ferramenta local e independente para pesquisar vagas e produzir um conjunto
estruturado que outra IA possa ler e filtrar. O projeto usa o Scrapling
`v0.4.15`, instalado a partir do clone oficial fixado em `vendor/Scrapling`.

## Uso rapido

Para abrir a interface local no navegador, execute na raiz da pasta:

```powershell
.\abrir-interface.ps1
```

O painel abre em `http://127.0.0.1:8765`, mostra os resultados existentes e
permite:

- configurar termos de busca, estágio/júnior, remoto/híbrido/presencial e
  cidades, estados ou Brasil;
- salvar essas preferências somente neste computador;
- iniciar uma nova busca pelo botão **Buscar vagas agora**;
- baixar as vagas em um relatório Markdown, separado por aderência.

Salvar a configuração não inicia uma busca automaticamente. O servidor aceita
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

## Limites de segurança

- Não acessa SQLite, Notion, RADAR, `pipeline-state.json` nem a pasta
  `Vagas Dev`.
- Não automatiza nem raspa o LinkedIn, preenche formulários ou envia candidaturas.
- A interface abre somente a página inicial oficial do LinkedIn após seu clique
  e mostra os termos para copiar. O Radar não lê a página nem acessa, captura ou
  armazena cookies/tokens; o navegador pode usar a sessão que já estiver aberta.
- Não contorna CAPTCHA, 2FA, rate limit, login ou alerta de atividade.
- Quando uma fonte exige autenticação, ela termina com handoff manual.
- Não grava cookies, tokens, senhas, perfis do navegador ou HTML integral nas
  saídas.
- Os rótulos de aderência são sinais determinísticos, não fatos nem decisões de
  candidatura.

`FIT:READY` significa somente **mais compatível no Radar local**. Ele não é o
estado `READY` canônico do funil/SQLite, não comprova vaga aberta e não autoriza
preenchimento, clique final ou envio de candidatura.

## Instalação

No PowerShell, a partir da raiz deste workspace:

```powershell
.\scripts\setup.ps1
```

O comando usa exclusivamente Python 3.13 em `job-radar-pilot\.venv`, instala o
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

Na interface, **Baixar relatório** transforma em Markdown exatamente as vagas
visíveis pelos filtros atuais. O documento separa mais compatíveis, condicionais,
dados insuficientes e fora do perfil; também registra os estados de cobertura de
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

`EMPTY` significa que a página declarou ausência de resultados. Se os seletores
esperados desaparecerem, o status é `ERROR/LAYOUT_CHANGED`, não vazio.
O coletor preserva o HTML integral recebido do Scrapling para o parsing. Os
marcadores de vazio são avaliados somente no texto visível, portanto conteúdo
em `script`, `style` ou elementos ocultos não declara `NO_RESULTS`.

## Paginação por fonte

- `next`: seletor do link da próxima página (programathor, casado-dev, seja-trainee).
- `declared_count`: total declarado pelo portal (99jobs, vagas-com).
- `single_page: true`: portal verificado com página 2 vazia/inexistente (otrainee, companhia-de-estagios).
- Ainda sem paginação observável (carregam mais por scroll/botão em JavaScript): estagiotrainee, eureca, ciee, nube, cia-de-talentos e infojobs; ficam `PARTIAL/PAGINATION_UNVERIFIED`.

O fallback adaptativo só é aceito na primeira página, sem marcador de vazio e com
pelo menos duas vagas válidas (sem link de login/listagem e título com 8+ caracteres).
Da página 2 em diante, zero cards configurados encerra a listagem.

## Fontes adicionadas em setembro/2026

nerdin, mytechjobs (iMasters), empregos-com, trampos, remotar e coodesh. Avaliadas e **não**
incluídas: GeekHunter, TalenTI, eu.dev.br, ViUmaVaga, Super Estágios, Futura Estágios e
Glassdoor (o `robots.txt` bloqueia acesso automatizado); GitHub `backend-br/vagas`
(`robots.txt` nega `/issues`); Catho (login e proteção anti-bot); Revelo (404);
Quero Vagas Tech, VagasPraJr e EmpregosTech (domínio não resolve).

## Rolagem, termos de busca e histórico

- `browser: {scroll_to_load: true}`: rola a página até a quantidade de cards estabilizar
  (eureca, nube, cia-de-talentos). No nube o limite é de 40 rolagens (~1.200 vagas mais
  recentes de ~3.500), então continua `PARTIAL` por escolha.
- `query_path: "/vagas-de-{query}"` ou `query_param: q`: fazem qualquer fonte receber a
  varredura de vários termos (vagas-com e infojobs já usam). O texto vira slug sem acento.
- Enriquecimento: vagas `CONDITIONAL`/`AMBIGUOUS` com tecnologia compatível têm a página de
  detalhe lida (HTTP estático, respeitando robots.txt e limites; ignora Indeed e fontes com
  login) e são reclassificadas; recebem `ENRICHED:DETAIL`. `collect --enrich-limit N`
  (padrão 40; `0` desliga).
- Histórico local em `%LOCALAPPDATA%\JobRadar\history.json` (só chave da vaga e data da
  primeira observação). Da segunda coleta em diante, vagas inéditas ganham `STATUS:NEW` e
  o selo "Nova" no painel. `collect --no-history` desliga.
- Agendamento diário no Windows (Agendador de Tarefas):
  `schtasks /Create /SC DAILY /ST 08:00 /TN "JobRadar" /TR "powershell -NoProfile -File \"<pasta>\buscar-vagas.ps1\" -Workers 3"`

## Fallback adaptativo de cards

Cada fonte aceita `adaptive: true|false` em `config/sources.yaml`; a ausência da
chave equivale a `true`. O coletor tenta sempre o seletor configurado primeiro.
Depois de extrair ao menos uma vaga válida, ele pode memorizar uma impressão
estrutural sanitizada do card e usá-la para relocalizar cards quando somente o
layout mudar. `adaptive: false` desliga tanto a leitura quanto a atualização
dessa memória para a fonte.

A memória fica em `%LOCALAPPDATA%\JobRadar\adaptive\adaptive.db` (ou
`~/AppData/Local/JobRadar/adaptive/adaptive.db` sem `LOCALAPPDATA`), nunca no
repositório. Ela contém apenas estrutura necessária à relocalização: não grava
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

## Preferências de busca

Use **Configurar busca** na interface. Os valores ficam em
`%LOCALAPPDATA%\JobRadar\search-preferences.json`, fora do repositório. As
consultas personalizadas são aplicadas às fontes que oferecem busca por texto;
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
sessão ficam em `%LOCALAPPDATA%\JobRadar\profiles`, fora do repositório e das
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

## Desenvolvimento e testes

```powershell
$env:PYTHONPATH = (Resolve-Path .\job-radar-pilot\src).Path
.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot\tests -v
```

Definir o `PYTHONPATH` dessa forma garante que os testes usem o código deste
workspace, mesmo quando a instalação editável da `.venv` ainda aponta para
outro checkout. Os launchers `run-job-radar.ps1` e `abrir-interface.ps1` fazem
essa priorização automaticamente.

Os testes de extratores usam fixtures locais sanitizadas. Apenas o smoke test
explicitamente executado acessa uma fonte pública.

Os seletores das 21 fontes habilitadas foram validados ao vivo em setembro de
2026 e têm testes determinísticos por comportamento. A fonte Vida de Trainee
fica desabilitada porque o arquivo observado estava parado em 2024. Portais
externos continuam sujeitos a mudanças de layout, bloqueios e paginação não
observável; nesses casos, o coletor retorna estado parcial ou erro explícito em
vez de declarar cobertura completa.

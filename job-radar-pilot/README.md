# Job Radar Pilot com Scrapling

Ferramenta local e independente para pesquisar vagas e produzir um conjunto
estruturado que outra IA possa ler e filtrar. O projeto usa o Scrapling
`v0.4.15`, instalado a partir do clone oficial fixado em `vendor/Scrapling`.

## Limites de segurança

- Não acessa SQLite, Notion, RADAR, `pipeline-state.json` nem a pasta
  `Vagas Dev`.
- Não pesquisa LinkedIn autenticado, preenche formulários ou envia candidaturas.
- Não contorna CAPTCHA, 2FA, rate limit, login ou alerta de atividade.
- Quando uma fonte exige autenticação, ela termina com handoff manual.
- Não grava cookies, tokens, senhas, perfis do navegador ou HTML integral nas
  saídas.
- Os rótulos de aderência são sinais determinísticos, não fatos nem decisões de
  candidatura.

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
habilitadas e não cria `FetchPolicy` nem realiza requisições.

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
  contagens, bloqueios e erros sanitizados.

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

## Autenticação manual

`AUTH_REQUIRED`, `LOGIN_REQUIRED`, `TWO_FACTOR`, `CAPTCHA` e
`ACTIVITY_ALERT` não são burlados. Abra a URL indicada no relatório, autentique
manualmente quando apropriado e só depois repita a fonte. O piloto não mantém
credenciais nem cookies no repositório ou nas saídas.

## Prompt curto para outra IA

> Leia `vagas.jsonl` linha por linha. Filtre oportunidades de estágio ou júnior
> em backend Java/Spring, compatíveis com trabalho no Brasil e com minha
> localidade. Trate `match_labels` apenas como sinais para revisão; confirme
> requisitos, senioridade, localidade e abertura usando os campos factuais e a
> `canonical_url`. Separe vagas aplicáveis, condicionais e ambíguas sem inventar
> informações ausentes.

## Desenvolvimento e testes

```powershell
.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot\tests -v
```

Os testes de extratores usam fixtures locais sanitizadas. Apenas o smoke test
explicitamente executado acessa uma fonte pública.

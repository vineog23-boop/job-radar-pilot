# Curadoria do Radar: uso, instalação e recuperação

Este guia acompanha a versão com quatro áreas. O procedimento abaixo não registra
uma implantação concluída nem substitui o resultado dos testes do código final.
O manual completo está em [README](../job-radar-pilot/README.md).

## Usar no dia a dia

1. Abra **Oportunidades** para avaliar vagas mais compatíveis, ainda não
   acompanhadas e com página de detalhes confirmada nos últimos sete dias.
   A confirmação é uma evidência recente; abra o portal para verificar se ainda
   aceita candidatura.
2. Abra **A conferir** quando faltar confirmar algum critério ou a
   disponibilidade. Uma lista vazia em Oportunidades não significa base vazia.
3. Salve uma vaga para levá-la a **Candidaturas**. Use **Me candidatei** depois
   de realizar a candidatura no portal. As etapas incluem entrevista, oferta e
   recusa; abrir o anúncio não registra candidatura automaticamente.
4. No título da vaga acompanhada, abra o detalhe para editar **Observação da
   candidatura** e clique em **Salvar observação**. A data da candidatura aparece
   quando já foi registrada. Candidaturas antigas/encerradas continuam acessíveis;
   filtros adicionais podem reduzir a lista. Descartadas ficam fora dessa área.
5. Escolha o formato e use **Exportar resultados (N)** junto à lista: leva a
   seleção atual completa, sua ordem e seus filtros, inclusive além das linhas
   já desenhadas. Seleção vazia gera arquivo sem vagas. Se a base mudar, atualize
   a seleção e tente novamente.

**Configurações** reúne perfil, fontes, importação manual, limpeza, verificação
de links e exportação automática. **Ver todos os resultados guardados** permite
diagnosticar vagas fora do foco. O painel avançado de exportação nessa área
monta outro recorte; seus filtros são independentes da lista atual.

## Configurar o foco e reaplicar a base

Antes de salvar um perfil sobre uma base importante, faça o backup descrito
abaixo. Aguarde qualquer busca/verificação terminar.

Em **Configurações → Configurar busca**:

- Marque **Somente desenvolvimento de software** se deseja esse foco. Suporte,
  infraestrutura, dados/BI, QA e segurança não viram programação apenas por
  mencionar Java/SQL; função genérica sem confirmação precisa de conferência.
- Para Java/Spring, defina **Java** e **Spring Boot** como tecnologias principais.
  O núcleo aceita evidência de uma dessas tecnologias, sem exigir ambas. Deixe
  SQL e ferramentas de apoio como complementares; não use “full stack” como
  núcleo se deseja restringir vagas júnior a Java/Spring.
- Se quiser, marque **Estágios em Inteligência Artificial** e **Estágios full
  stack** com o foco de desenvolvimento ativado. As exceções valem somente para
  estágio explícito, não para júnior/pleno/sênior, trainee ou aprendiz. Não anulam
  local, modalidade, níveis ou exclusões configurados.
- Confira localidades, modalidade, níveis e termos. **Ver impacto** permite
  conferir a mudança antes de gravar. **Salvar configurações** reaplica o perfil
  às vagas guardadas sem nova coleta; não é necessário buscar tudo novamente.
  Vagas do cesto da coleta são reavaliadas e podem voltar se passarem nas regras.

Essas opções são escolhas do perfil local. Não há alteração automática das
preferências pessoais em `config/profile.yaml`. Só salvar o perfil não apaga
as vagas fora do foco.

Em **Configurações → Limpeza**, **Fora das tecnologias principais e dos estágios
que considero** é uma regra opcional (`other_stack`), desligada por padrão.
Ativá-la autoriza descartar `OTHER_STACK` nas coletas seguintes; ocultação nas
áreas de curadoria funciona independentemente dela. Consulte a prévia e os
exemplos antes de limpar a base existente. Vagas acompanhadas são protegidas,
exceto quando você pede expressamente a remoção das descartadas. Desfazer última
limpeza não substitui o backup completo.

## Antes de atualizar: backup privado

1. Espere terminar busca/verificação e feche o painel pelo terminal que o abriu.
   Suspenda apenas as rotinas de vagas que possam escrever na mesma saída.
2. Anote a versão anterior e a pasta da instalação. Faça uma cópia datada fora
   do repositório de **todo o conjunto**:
   - `job-radar-pilot/output/`;
   - pasta de dados locais: no macOS, normalmente
     `~/Library/Application Support/JobRadar`; no Windows,
     `%LOCALAPPDATA%\JobRadar`;
   - pasta de exportações escolhida em Configurações.
3. `LOCALAPPDATA` explícito prevalece também no Mac. Confirme a pasta efetiva
   antes de copiar. Os dados incluem preferências, perfis, regras, tracking e
   histórico; perfis de navegador podem conter cookies. Mantenha a cópia privada.
4. Confira os arquivos copiados e valide a saída. Uma cópia feita durante escrita
   não é uma recuperação confiável. Não publique dados/credenciais junto ao código.

## Abrir a versão aprovada

Instale somente depois da validação da composição exata de código escolhida.
Uma PR anterior, `main` e commits locais podem conter conjuntos diferentes.
Não troque a instalação ativa apenas pelo nome da branch. Preserve alterações
existentes e não use `reset --hard` ou remoção de dados para preparar a atualização.

### macOS

Requisitos: Python **3.13** e Git. Na raiz da instalação aprovada, que contém
`scripts/`, o launcher e a pasta Python aninhada:

```bash
bash ./scripts/setup-mac.sh
./"Radar de Vagas.command"
```

O setup prepara `.venv` e Scrapling 0.4.15, instala navegadores e cria o atalho na
Mesa. Em um checkout de teste, direcione o atalho para uma pasta temporária com
`JOBRADAR_SHORTCUT_DIR`; o setup normal sobrescreve o atalho com o caminho do
checkout onde foi executado. Não faça essa troca antes de aprovar a versão.

Feche o processo antigo antes de reabrir após atualização. O launcher reconhece
projeto/venv e pode reutilizar um painel que ainda está executando código antigo.
Se outra aplicação ocupar a porta 8765, resolva o conflito sem encerrar processos
desconhecidos. O log fica na pasta de dados locais, em `logs/interface.log`.

### Windows

Instale Python **3.13** e Git; depois abra **Radar de Vagas.cmd** na raiz. Na
primeira execução ele chama o setup. Pelo PowerShell, os equivalentes são:

```powershell
.\scripts\setup.ps1
.\abrir-interface.ps1
```

O ícone pode ser criado com **Criar atalho na area de trabalho.cmd**. Feche a
janela do painel antigo e reabra após a atualização. Os comandos precisam ser
validados em Windows antes de entregar uma release para esse sistema.

## Conferência técnica antes de liberar

A `.venv` deve ser a da instalação aprovada, com Python >=3.13,<3.14. Não copie
uma venv entre sistemas ou presuma que uma instalação editável compartilhada
aponta para o checkout correto: use `PYTHONPATH` para executar o código escolhido.
No checkout de validação, use dados/saída temporários e não inicie coleta real
ou Telegram como parte dos testes offline.

Na raiz Git, macOS:

```bash
export PYTHONPATH="$PWD/job-radar-pilot/src"
job-radar-pilot/.venv/bin/python -m pip check
job-radar-pilot/.venv/bin/python -m ruff check job-radar-pilot/src job-radar-pilot/tests --config job-radar-pilot/pyproject.toml
job-radar-pilot/.venv/bin/python -m pytest job-radar-pilot/tests -q -p no:cacheprovider
job-radar-pilot/.venv/bin/python -m job_radar.cli collect --dry-run --no-history --no-export
job-radar-pilot/.venv/bin/python -m job_radar.cli validate-output job-radar-pilot/output/vagas.jsonl
```

O último comando exige um JSONL existente; valide a cópia do backup quando
estiver preparando a recuperação. `collect --dry-run` valida/lista fontes sem
consulta aos portais; o modo de mesmo nome do Hermes não garante ausência de rede.

No PowerShell, para conferir o código local após instalar também as dependências
de desenvolvimento:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'job-radar-pilot\src'
.\job-radar-pilot\.venv\Scripts\python.exe -m pip install -e 'job-radar-pilot[test]'
.\job-radar-pilot\.venv\Scripts\python.exe -m pip check
.\job-radar-pilot\.venv\Scripts\python.exe -m ruff check job-radar-pilot/src job-radar-pilot/tests --config job-radar-pilot/pyproject.toml
.\job-radar-pilot\.venv\Scripts\python.exe -m pytest job-radar-pilot/tests -q -p no:cacheprovider
```

Revise regressões de foco (`test_focus_policy.py`), jornada
(`test_focused_workspace.py`), reclassificação, limpeza, tracking e exportação;
rode a suíte completa do código final. Compare também a avaliação do classificador
antes/depois com o mesmo perfil e amostra. Registre os resultados reais; este
guia não declara esses testes concluídos.

No piloto, confirme notas/datas, candidatura antiga, filtros entre áreas,
exportação vazia e URLs/ordem na planilha, além de teclado e tela reduzida. Só
depois reative os horários existentes. Hermes precisa apontar para a pasta Python
aninhada e a mesma saída do painel; seus critérios pessoais e `--no-export`
continuam independentes das escolhas visuais. Não duplique a rotina com outro
agendador. No Windows, `scripts/agendar-coleta.ps1 -Horario 08:00` cria a tarefa e
`-Remover` a remove; mantenha o horário escolhido pelo usuário.

## Voltar à versão anterior sem perder candidaturas

1. Pare novamente painel e escritores; preserve uma cópia do estado posterior,
   incluindo notas e candidaturas recentes.
2. Prepare o código anterior sem apagar alterações existentes. Se não houve
   mudança incompatível de dados, prefira voltar só o código e manter as ações
   recentes. Caso contrário, teste a recuperação do conjunto completo em pastas
   separadas e concilie as ações feitas depois do backup.
3. Se usar outro checkout, prepare nele a saída validada e confira a pasta de
   dados locais. Atualize o atalho e os caminhos do Hermes em conjunto; trocar
   somente o launcher pode mostrar uma base vazia ou deixar a automação no código
   novo. Reconstrua a venv quando necessário, sem apagar dados do usuário.
4. Valide a saída e uma candidatura conhecida antes de reativar a agenda. Não
   restaure apenas `vagas.jsonl` ou `tracking.json` sem conferir o restante do
   conjunto. Não edite um arquivo ilegível para virar `{}` e não apague travas
   para forçar operações.

O painel é local em `http://127.0.0.1:8765`. O computador precisa estar disponível
para coletas agendadas; layout adaptável não oferece acesso remoto pelo celular.


## Registro da aplicação local — 17/10/2026

A versão foi aplicada no macOS depois de 1.325 testes aprovados e quatro ignorados.
Ruff, dependências, sintaxe JavaScript e schema das 630 linhas finais foram conferidos.
O CI no Windows ainda deve ser acompanhado antes de instalar em outra máquina.

Foram mantidas as localidades e modalidades existentes. O foco pessoal usa Java e
Spring Boot, com exceções somente para estágios IA/full stack e exclusões .NET/C#.
Os termos genéricos de TI foram substituídos por buscas relacionadas a esse foco.
A prévia real foi de 1.085 para 630 registros: 334 fora do perfil, 119 de outra stack,
um fora de TI e um encerrado foram arquivados. As dez candidaturas e suas notas
permaneceram intactas; o YAML pessoal também permaneceu igual.

A tela inicial mostrou 11 oportunidades com detalhe confirmado nos últimos sete dias;
603 ficaram em A conferir por algum critério ou disponibilidade ainda incerto.
Esses números são um retrato dos dados salvos, sem nova consulta aos portais.
Na verificação manual, filtrar Spring produziu seis resultados e a planilha baixada
conteve exatamente esses seis. A recuperação foi testada na cópia isolada antes
da limpeza real; há backup completo separado e também o Desfazer última limpeza.

Referência de acessibilidade usada para rótulos e agrupamentos:
[W3C — Labeling Controls](https://www.w3.org/WAI/tutorials/forms/labels/) e
[W3C — Grouping Controls](https://www.w3.org/WAI/tutorials/forms/grouping/).

# Radar de Vagas confiável

Autorização: o usuário pediu compreender o projeto e depois corrigir e melhorar autonomamente o fluxo buscar → filtrar → salvar → acompanhar → exportar, pensando como candidato. A auditoria anterior reproduziu perda de registros salvos, exportação divergente, perfil desatualizado, falso positivo de disponibilidade e limitações no macOS. Preservar a arquitetura e o visual existentes; entregar melhorias concretas sem reconstruir o produto.

## Requisitos

1. Buscas parciais, bloqueadas ou interrompidas preservam registros anteriores sem renovar sua data de observação. Mesmo uma busca completa que não reencontra uma vaga mantém seu registro completo se ela estiver no acompanhamento. Dados corrompidos nunca autorizam sobrescrita destrutiva. Alterações simultâneas no acompanhamento não perdem entradas.
2. A exportação da tabela contém exatamente todas as vagas filtradas, na ordem exibida, inclusive além da paginação. Não confiar em registros enviados pelo navegador: receber uma seleção ordenada de URLs e carregar os registros canônicos. Exportações gerais continuam disponíveis. Melhores vagas excluem encerradas independentemente do filtro de idade. Pontuação e limites temporais consistentes.
3. Disponibilidade é evidência, não promessa. Página institucional, login ou CAPTCHA nunca confirma vaga. Verificação recente de link prevalece sobre inferências por data, mantendo prazo vencido como encerrado. Disponibilizar a verificação limitada de melhores vagas na interface, com progresso, bloqueio de concorrência e resultados LIVE/DEAD/UNKNOWN traduzidos sem exageros.
4. Perfil permite escolher stack principal explicitamente, separada das tecnologias complementares, além dos níveis/modelos/locais já existentes. Um complemento genérico não torna uma vaga de outra stack compatível. Trocar ou salvar perfil reavalia resultados existentes sob o mesmo bloqueio de saída da coleta; se ocupado, retornar erro claro e não gravar parte da alteração. Preferências antigas continuam válidas.
5. Salvas e candidaturas dão acesso ao histórico inteiro; o usuário pode refinar depois. Sincronizar alterações entre abas. Preservar foco do teclado ao expandir ou acompanhar vagas. Controles de exportação explicam seleção e contagem; lembrar portais escolhidos; melhorar progresso sem falsa estimativa. Corrigir checkbox e estados vazios/confusos. Oferecer acesso explícito às vagas sem data de publicação, sem fabricar datas para passar filtros.
6. Instalação e atalho macOS reproduzíveis e versionados, abrir pasta de exportação no Finder, dados locais em Library/Application Support preservando overrides. Manter Windows e adicionar CI macOS. Documentar fluxo e limites dos portais, sem afirmar cobertura completa nem precisão medida sem ground truth.

7. Integrar páginas públicas InHire por empresa (Programmers/Bionexo), listagem CI&T sem acessar detalhes restritos e API pública Greenhouse por board (AB InBev), com fixtures sanitizadas e coleta isolada de validação. Documentar alcance por empresa, não cobertura de todo ATS. 99Freelas é trabalho freelance separado; Telegram requer canais públicos especificados; LinkedIn permanece manual. Fontes existentes não devem ser duplicadas.

## Restrições globais

- Python >=3.13,<3.14; Scrapling==0.4.15; não editar vendor/.
- Não alterar config/profile.yaml nem dados pessoais reais durante testes.
- Não raspar LinkedIn nem contornar robots, CAPTCHA ou login; respeitar intervalos.
- Preservar launchers Windows e preferências antigas; JSONL validado pelo schema existente.
- Compartilhar OutputLock em todas as mutações de vagas; ocupado retorna HTTP 409.
- Corrupção do acompanhamento impede limpeza e reescrita destrutiva.
- Interface, documentação e commits em português brasileiro; não versionar dados/exportações do usuário.
- Testes isolados; executar avaliação do classificador antes/depois sem alegar acurácia sem amostra rotulada.
- Trabalhar em feat/radar-confiavel; não publicar nem mesclar em main automaticamente.

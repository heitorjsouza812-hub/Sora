# Etapa 4 (passo 6): ligar as peças no worker

Pedido do Heitor em 2026-11-02, depois da etapa 3. Ramo: `etapa4-pecas`, numa worktree separada em `C:\dev\sora-e4`, criada a partir de `etapa3-motor` enquanto a revisão final da etapa 3 termina; o orquestrador junta as correções da etapa 3 nele (nada de push; o orquestrador cuida disso). Trabalhe só em `C:\dev\sora-e4`.
- Portas: a etapa 3 ainda usa 8000/5173 para o e2e. Até o orquestrador avisar, rode API e app desta worktree em outras portas (ex.: API 8100, Vite 5273).

**Teste de pronto:** com `SORA_MODELO_FALSO=1`, uma cadeia real usa o navegador por árvore (com revisão de domínio novo em perfil logado), memória, pendências, rotina agendada (perfil efêmero), canal de equipe com delegação e o catálogo preguiçoso; tudo aparece no app (painel Trabalho, cartões, canais), sobrevive a reiniciar o worker e não perde dado.

## Regras para todo o time

As mesmas de `log/etapa3-motor.md` ("Regras para todo o time"), mais:

- Fonte da verdade: `docs/plano-de-implementacao/02-especificacao-do-backend.md`, `docs/referencias/rakazo.md`, `docs/referencias/openbot.md` (seções "Antes de ligar em produção"), `docs/referencias/agent-desktop.md`.
- **Arquivos compartilhados** (`workers/__main__.py`, `workers/fila.py`, `workers/conversa.py`, `workers/cadeia.py`, `app/ferramentas/registro.py`, `app/revisor/politica.py`, `app/agentes/montagem*`): edição pequena e aditiva, commit imediato só daquele arquivo, e registre o gancho em `.maestri/contrato-etapa4.md`. Prefira criar seu próprio módulo e ligá-lo com uma linha.
- Sem simulação: cada peça ligada tem teste com banco real (Docker) e worker real; o que não der para testar sem chave de terceiros (Telegram, voz, MCP remoto) fica atrás de configuração, desligado por padrão, com teste do caminho desligado e do caminho ligado contra um servidor local.
- Produção nunca liga sozinha o que precisa de host separado (`executar_comando` com Docker, Chromium local).

## Divisão

| Agente | Escopo exclusivo |
|---|---|
| **Leme** | Navegador no worker: itens (a) a (e) do Faro em `openbot.md`; ferramentas `navegador_*` por árvore no catálogo no lugar de `navegador_ler`/`navegador_agir`; `MotorPlaywright` e `GerenteAbas` no startup do worker (CDP em produção); `RevisaoNavegacaoNecessaria` pausa a etapa e vira cartão de aprovação; `POST /v1/aprovacoes/{id}/decidir` grava `aprovar_dominio`; clique que cai em domínio barrado vira pedido de revisão; rotinas com `sem_supervisao=True`; evento `navegador.aba` e rastro no painel Trabalho; "assumir aba". `app/navegador/**`, `app/ferramentas/navegador*`. |
| **Tear** | Peças do OpenBot no banco: `ArmazemFila`, `ArmazemCanais` (cada turno numa transação com `SELECT ... FOR UPDATE`, mãe primeiro; grava `turno_seq` e `fim_no_turno_do_pai`), `ArmazemReacoes`, transferências do correio; `app/api/equipe.py` sem `NotImplementedError`; `app/eventos/equipe.py`; no worker, `FilaAgente.proximos` antes do turno, `recuperar_apos_queda` da fila e dos canais ao subir, turno curto do líder para `precisa_lider`; ferramentas `reagir`, `canal_*` em `ESQUEMAS`. `app/filas/**`, `app/canais_equipe/**`, `app/correio/**`, os repositórios novos. |
| **Âncora** | Peças do Rakazo dentro do turno do agente: medidor de contexto depois de cada chamada e compactação antes do turno (`app/contexto`, `app/memoria/compactacao.py`, job `compactar_historico`); limite de saltos; catálogo preguiçoso; política + juiz do revisor na execução de cada ferramenta (falha fechada); memória (`lembrar`, `buscar_memoria`, `esquecer_memoria`; vetor no pgvector com o provedor de embeddings do usuário quando houver, senão por palavras, testado com banco real); `buscar_historico`/`ler_historico`; `catalogo_tarefas`; `propor_instrucoes`; pendências; habilidades (`/Nome`, `@Nome`); `instrucoes.py`; `enviar_para_agente`. `app/agentes/**`, `app/contexto/**`, `app/memoria/**`, `app/pendencias/**`, `app/habilidades/**`, `app/revisor/{juiz,acoes}.py`, as ferramentas correspondentes. |
| **Relógio** | Rotinas e canais externos: `executar_rotina` agendada pela tabela `rotinas` (cron do ARQ ou laço próprio, sem duplicar execução entre workers), `SEM_RESPOSTA`, sempre sem supervisão; `reconciliar_travados` periódico; Telegram (`responder_canal`) atrás de `TELEGRAM_*`; conectores MCP do usuário com catálogo preguiçoso e prazo; `executar_comando` só com `SANDBOX_PROVEDOR=docker` (desligado em produção sem host separado); voz (`falar`, transcrever) com a chave do usuário; rotas que faltarem para rotinas, conectores e habilidades. `app/rotinas/**`, `app/canais/**`, `app/conectores/**`, `app/computador/**`, `app/voz/**`, `app/api/{canais,rotinas,conectores,habilidades}.py`. |
| **Vitral** | App: telas para o que os quatro acima expuserem, sem mudar tokens nem mascote: rastro do navegador e "assumir aba" no painel Trabalho, cartão de revisão de domínio, canais de equipe (Parar/Retomar/Reatribuir), memória, rotinas, conectores e habilidades em Configurações, medidor de contexto. Comece pelo contrato em `.maestri/contrato-etapa4.md`; o que ainda não tiver rota, espere. `app/src/**`, `app/qa/**`. |

**Pronto de cada peça:** teste de integração com Docker e worker real; e2e do app no fim.

## Validação

Aferidor valida cada bloco quando o dono avisar e, no fim, a etapa inteira (mesmo formato de `validador-final-2.md`), em `.maestri/relatorios/validador-etapa4*.md`. Reprovou, volta para o dono.

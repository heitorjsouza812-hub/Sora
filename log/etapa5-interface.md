# Etapa 5: interface nova (bots e grupos)

Pedido do Heitor em 2026-11-02 e decisões de 2026-11-04. Ramo `etapa5-interface`, worktree `C:\dev\sora-e5` (criada da `main` em `b46518b`). Nada de push: o orquestrador cuida disso depois do "sim" do Heitor.

## Por que

A interface atual (projetos com plano, cartões de etapa e "Aprovar e publicar") ficou confusa. A referência de experiência é o **Grok Bot** (xAI) e o **OpenBot**: bots persistentes criados por conversa, grupos de bots com um chefe de equipe, cartões de aprovação no lugar de "publicar". **Só a ideia:** o Grok Bot é proprietário e o OpenBot é PolyForm Noncommercial; nenhum texto, código, ícone ou imagem deles entra no repositório.

## Decisões (Heitor, 2026-11-04)

1. **A Sora é sempre a chefe de equipe dos grupos.**
2. **"Projetos" some e vira grupo.** Pedido grande à Sora → ela propõe um grupo, reaproveita bots que já existem e só cria bot novo depois do "sim".
3. **Tela Plugins escondida** até o grupo decidir.
4. **Sem protótipo:** pode alterar direto.
5. **Ilha da Sora só fora do app:** no desktop (Tauri) aparece só com a janela principal fora de foco ou minimizada; dentro do app e no navegador web não aparece.

## Como fica

- **Barra lateral:** Sora (conversa principal e chefe de equipe) no topo · **Bots** (cor, estado: trabalhando / precisa de você) · **Grupos** (com destaque em quem precisa de você) · busca **Ctrl+K** · **Configurações**. Saem Projetos, Revisão, Plugins (escondido) e o "Aprovar e publicar".
- **Criar bot conversando:** o usuário pede à Sora; ela devolve um **cartão de rascunho** com seções (nome, função, cor, instruções, ferramentas, rotina) que o usuário ajusta e confirma. O formulário do bot continua para editar depois.
- **Tela do bot (1:1):** conversa no centro; ao lado: trabalho (navegador, captura, passos), rotinas, memória, pendências, contexto, ferramentas. **Microfone só aqui.**
- **Grupos:** Novo grupo → 2 a 6 bots → nome editável; a Sora entra como chefe. `@bot`, `@todos`, responder a uma mensagem; **repasses aparecem como mensagens**; no topo a lista de membros mostra quem trabalha, com **Parar**.
- **Aprovação sem "publicar":** ação que mexe no mundo vira cartão **"Precisa de você"** (Enviar/Descartar ou Aprovar/Recusar). Resultado chega como **mensagem com arquivos**.

## Regras para todo o time

As de `log/etapa4-pecas.md`, mais:

- Trabalhe só em `C:\dev\sora-e5`. **Portas desta etapa:** API **8200**, Vite **5383**, Postgres `sora-e5-pg` (127.0.0.1:46432), Redis `sora-e5-redis` (127.0.0.1:57379), `backend/.env` já aponta para eles. Não use 8100/5273 nem os bancos `sora-e4-*`.
- Sem simulação e sem conteúdo de demonstração. Tudo em PT-BR. Não mudar a aparência do mascote nem as cores dos agentes.
- Arquivos compartilhados: edição pequena e aditiva, commit só daquele caminho, registre o gancho em `.maestri/contrato-etapa5.md`.
- Commit só dos seus caminhos (`git commit -- caminhos`), mensagem em PT-BR. Sem push.
- Antes de commitar no app: `npm run build`, `npx oxlint`, `npm test`. No backend: `uv run ruff check`, `uv run ruff format --check`, seus testes (unitários e de integração com o Docker desta etapa).
- Ao terminar cada rodada: relatório em `.maestri/relatorios/<seu-nome>.md` e `maestri ask "Claude Code rei" "<resumo>"`.

## Divisão

| Agente | Escopo exclusivo |
|---|---|
| **Âncora** (backend) | Sora persistente por usuário como agente (chefe de equipe) e líder padrão de todo grupo; grupos sobre `canais_equipe` (criar com 2–6 bots, renomear, membros); proposta de grupo pela Sora para pedido grande (cartão "Montar grupo" com bots reaproveitados/novos; bot novo só com "sim"); criação de bot por **rascunho** (ferramenta da Sora + rota para confirmar com ajustes); ferramentas no `AgenteSaida`; estado "precisa de você" por bot e por grupo (evento SSE); entrega como mensagem com anexos no grupo/chat; o caminho "projeto/cadeia" deixa de ser a entrada do app (código pode ficar, sem rota de publicar). `backend/app/**`, `backend/workers/**`, `backend/tests/**`, `backend/prompts/**`. |
| **Leme** (app: casca e bots) | `App.tsx`, layout e barra lateral (Sora · Bots · Grupos · Ctrl+K · Configurações), tela da Sora, tela do bot (1:1 com painel lateral), cartão de rascunho de bot, esconder Plugins, remover Projetos/Revisão/"Aprovar e publicar"; estado compartilhado (`state/**`) com edição aditiva para o Mosaico. `app/src/App.tsx`, `app/src/components/layout/**`, `app/src/components/builder/**`, `app/src/screens/{Home,SoraChat,AgentChat,Agentes,CriarAgente,Projetos,Revisao,Plugins}.tsx`, `app/src/state/**`. |
| **Mosaico** (app: grupos e cartões) | Tela de Grupos (a partir de `Canais.tsx`): novo grupo 2–6 bots, renomear, `@menção`/`@todos`/responder, repasses visíveis, lista de membros com estado e Parar; cartões "Precisa de você" (Enviar/Descartar, Aprovar/Recusar) usados no chat do bot, no grupo e na Ilha. `app/src/screens/Canais.tsx` (vira Grupos), `app/src/components/equipe/**`, `app/src/components/pendencias/**`, `app/src/components/grupos/**` (novo). |
| **Vela** (Ilha) | Ilha só fora do app: Tauri mostra/oculta a janela da Ilha pelo foco/minimização da janela principal; dentro do app não renderiza; web não renderiza. Ilha mostra quem trabalha e o que precisa de você (cartões do Mosaico). `app/src/components/ilha/**`, `app/src-tauri/**`, `app/qa/ilha.mjs`. |
| **Prumo** (validador) | Valida cada bloco quando o dono avisar e, no fim, a etapa inteira, mais o teste com modelo real (Groq). Nunca edita código de produção. `.maestri/relatorios/validador-etapa5.md`. |

## Pronto da etapa

- Usuário novo: entra, conversa com a Sora, cria um bot conversando (cartão de rascunho), cria um grupo com 2 bots, pede algo no grupo, vê os repasses e o resultado chegar como mensagem com arquivo, aprova uma ação externa por cartão, nunca vê "publicar".
- Pedido grande à Sora vira proposta de grupo; bot novo só com "sim".
- Ilha some com o app em foco e aparece com ele fora de foco (Tauri real).
- Suíte do backend com integração, app build/oxlint/testes, e2e reescrito para o fluxo novo, ilha, test:visual com as telas novas conferidas, e teste com modelo real (Groq) ao vivo.

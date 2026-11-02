# Etapa 3: motor de ponta a ponta

Pedido do Heitor em 2026-11-01. Ramo: `etapa3-motor` (nada de push; o orquestrador cuida disso).

**Teste de pronto:** digitar "crie uma campanha para minha cafeteria" no app e ver agentes reais trabalhando e entregando, primeiro com `SORA_MODELO_FALSO=1`, depois com chave real.

## Regras para todo o time

- Leia `CLAUDE.md` §1, §2 e §6, e `log/ONDE-PARAMOS.md`. Fonte da verdade: `docs/plano-de-implementacao/02-especificacao-do-backend.md`.
- Mexa só nos arquivos do seu escopo. Precisa de algo de outro escopo? Peça a quem é dono ou ao orquestrador.
- Commit só dos seus arquivos, com `git add <caminhos>` (nunca `git add -A`), no ramo `etapa3-motor`. Sem push, sem rebase, sem trocar de ramo.
- Sem "feito" sem prova: rode `uv run ruff check app tests workers`, `uv run ruff format --check` e `uv run pytest` no backend (ou `npm run build`, `npx oxlint`, `npm test` no app), e cole o resultado real no relatório. Teste que falhou ou foi pulado é informado como tal.
- Sem mock do que dá para testar de verdade. Docker: `infra/docker-compose.dev.yml`.
- Não mexa em plugins, nome, nicho nem cobrança. Não mude a aparência do mascote.
- Economize cota: não leia o repositório inteiro, não rode a suíte inteira a cada edição.
- Ao terminar: escreva o relatório em `.maestri/relatorios/<seu-nome>.md` (o que fez, commits, resultado dos testes, o que ficou pendente) e rode `maestri ask "Claude Code rei" "<resumo>"`. Se a cota estiver acabando, avise antes de parar.

## Fase A: decisões de segurança do navegador (Cerca)

Decisões do Heitor, já tomadas:

**A1. Domínio novo com perfil logado passa por revisão.**
- Com perfil que tem login salvo, abrir um domínio ainda não aprovado para aquele perfil vale como política `revisor`, em toda ferramenta que navega (`navegador_abrir` e navegação via `navegador_acao`/`navegador_lote`). Compare por domínio registrável; aprovação fica guardada por perfil.
- A decisão depende do contexto (perfil + URL), então `politica_da_ferramenta(nome)` não basta: crie a checagem contextual e use-a no ponto em que a ferramenta executa.
- Perfil sem login continua como está.

**A2. Rotinas usam perfil sem login.**
- Execução sem supervisão sempre abre um perfil efêmero, sem estado salvo, ignorando a escolha de perfil do agente. Sem exceção por configuração.
- Teste que prove: rotina de agente com perfil logado não vê os cookies dele.

**A3. Navegador isolado em produção.**
- Chromium fora do worker, em contêiner próprio em `infra/docker-compose.yml`, em rede `internal: true` sem rota para `postgres`, `redis`, `api` nem metadados de nuvem.
- Toda saída passa por um proxy de saída (contêiner com perna na rede externa) que resolve o DNS ele mesmo e recusa IP privado, loopback, link-local e metadados **depois** de resolver. Isso fecha DNS rebinding e WebSocket, que o `context.route` não pega. Chromium sem QUIC e sem WebRTC por UDP direto.
- O worker conecta ao Chromium por CDP numa rede de controle. Contêiner sem root, `cap_drop: ALL`, limites de memória e CPU, imagens fixadas por digest.
- Em produção, o backend **recusa subir** o navegador se não houver endpoint remoto configurado (nada de Chromium local como fallback). Em dev, o Chromium local continua permitido.
- Prova com Docker real: de dentro do contêiner do navegador, `postgres`, `redis`, `169.254.169.254` e um nome que resolve para IP privado falham (HTTP e WebSocket), e um site público funciona. Deixe isso num script em `infra/scripts/`.

Escopo: `backend/app/revisor/politica.py`, `backend/app/navegador/**`, `backend/app/core` (só a config do navegador), `infra/**`, testes correspondentes, `docs/referencias/openbot.md` (atualizar "Antes de ligar em produção").

## Fase B: motor (passos 1 a 4)

### Trilho: passo 1, conversas e eventos
`backend/app/api/{conversas,cadeias,entregas,perguntas,aprovacoes,agentes,anexos,uso}.py`, os repositórios que elas usam, SSE (`api/eventos.py`). Enviar mensagem grava e enfileira; `eventos` entrega ao vivo com retomada. Spec §2, §3.

### Motor: passos 2 e 3, agente e cadeia
`backend/app/agentes/**` (montagem, middlewares, aparência), `backend/app/orquestrador/**`, `backend/workers/**`, `backend/app/sistema1/` só o que falta para o fluxo. Spec §6 e §6.1. Modo Cadeia completo: planejar, criar especialistas, executar etapas (até 3 em paralelo), verificar, entregar a resposta final. O `laya.py` e o `treino.py` não entram (são de fases futuras).

### Ferramentas: passo 4, ferramentas da fase 1
`backend/app/ferramentas/{buscar_web,ler_pagina,ler_anexo,entregar,escrever_arquivo,perguntar,falar,criar_agente,disparar_especialista,ver_especialista,mensagem_especialista,parar_especialista,veredito,permissoes,gerar_imagem}.py`, `registro.py`, `rotulos.py`, `backend/app/llm/imagem.py`. Spec §4. O que precisar de `ctx` do worker segue a interface em `ferramentas/base.py`; combine com o Motor.

### Divisão por agente (vale sobre os blocos acima)

| Agente | Escopo exclusivo |
|---|---|
| **Trilho** | `api/{conversas,cadeias,eventos}.py` e os repositórios que elas usam |
| **Balcão** | `api/{entregas,perguntas,aprovacoes,agentes,anexos,uso}.py` |
| **Molde** | `agentes/**` (montagem, middlewares, aparência) |
| **Compasso** | `orquestrador/**`, `workers/**`, o que falta em `sistema1/`; dono do teste de integração de pronto |
| **Prumo** | `ferramentas/{buscar_web,ler_pagina,ler_anexo,escrever_arquivo,gerar_imagem,falar}.py`, `llm/imagem.py` |
| **Elo** | `ferramentas/{entregar,perguntar,veredito,criar_agente,disparar_especialista,ver_especialista,mensagem_especialista,parar_especialista,permissoes}.py`, `registro.py`, `rotulos.py` |

A Cerca segue na Fase A ao mesmo tempo, no navegador e na infra. Todos usam a mesma pasta: rode só os testes do seu escopo, e se o `git commit` esbarrar em `index.lock`, espere uns segundos e repita. Falha em arquivo de outro dono não é sua: avise o dono.

**Contrato entre eles:** Trilho enfileira `planejar_cadeia`/`executar_etapa` e lê as tabelas; Motor grava estados e emite eventos pelo `app/eventos`; Ferramentas recebem o contexto de `ferramentas/base.py`. Mudou algo do contrato? Registre em `.maestri/contrato-etapa3.md` e avise os outros dois.

**Não entra nesta etapa:** ligar as peças de Rakazo, OpenBot e navegador por árvore (passo 6), e `app/api/equipe.py`.

**Pronto da fase B:** teste de integração com Docker e `SORA_MODELO_FALSO=1`: `POST` de mensagem → eventos SSE do plano, dos agentes e das etapas → entrega → cadeia `concluida`.

## Fase C: passo 5, app (Vitral)

`app/src/**`: trocar `data/planejador.ts` e o relógio de `state/projetos.ts` pelo backend, com SSE no chat, painel Trabalho e ilha. Spec §3. Sem modo demonstração. Mesmas telas e tokens; a aparência não muda. Testes do store atualizados, `qa/e2e.mjs` e `qa/ilha.mjs` contra o backend real com modelo falso. Depois, atualize `CLAUDE.md` §1 e §7, e copie para `AGENTS.md`.

## Validação

Validador independente roda ao fim de cada fase. Nunca edita código de produção; escreve o veredito em `.maestri/relatorios/validador-<fase>.md`. Reprovou, volta para o dono.

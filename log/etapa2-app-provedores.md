# Etapa 2 — Ligar o app às rotas de provedores (APP-001)

_Combinado em 2026-10-17 pelo orquestrador. Base: `docs/plano-de-implementacao/02-especificacao-do-backend.md` §3 (contrato com o app), §5 (como conectar) e §8.2 (login). Backend da etapa 1 já pronto: `log/etapa1-conexao-apis.md`._

**Objetivo:** as chaves de API saem do navegador. O app passa a ter login de verdade e a tela Configurações → Modelos de IA fala com `GET/POST/PATCH/DELETE /v1/provedores`, `GET/PATCH /v1/modelos` e `PATCH /v1/preferencias`.

**Fora desta etapa (não mexer):** chat/planejador/Trabalho/Ilha continuam simulados (`state/projetos.ts`, `data/planejador.ts`); SSE; créditos→Uso; plugins (congelados). Não mudar mascote nem cores dos agentes. Tudo em PT-BR.

## Regras

1. **Cliente HTTP** `app/src/api/cliente.ts`: base `import.meta.env.VITE_API_URL` (padrão `''` = mesma origem; no dev o Vite faz proxy de `/v1` → `http://localhost:8000`). Token de acesso **só em memória**. 401 → uma única renovação em voo (`POST /v1/auth/renovar`, `credentials: 'include'`) e repete o pedido uma vez; falhou → sessão encerrada → tela Entrar. Erros viram `ErroApi { status, mensagem }` com a mensagem PT-BR do backend (`detail`); 429 lê `Retry-After`; rede fora → "Não foi possível falar com o servidor da Sora."
2. **Desktop (Tauri):** cabeçalho `X-Sora-Cliente: desktop`; o token de renovação vem no corpo e fica no **cofre do sistema** (Credential Manager) por comandos Rust `cofre_ler`/`cofre_gravar`/`cofre_apagar` expostos em `src/desktop/ponte.ts` (no navegador: não existem, usa cookie). Nunca em `localStorage`. Capability só da janela `main`. CSP: `connect-src` inclui a URL da API (dev: `http://localhost:8000`).
3. **Sessão** `app/src/state/sessao.ts`: `{ estado: 'carregando' | 'anonimo' | 'logado', usuario?: {nome, email, prioridade, tem_provedor} }` via `GET /v1/eu`. Na abertura tenta renovar em silêncio.
4. **Telas:** Entrar / Criar conta (`POST /v1/auth/entrar`, `/cadastrar` com `{nome,email,senha,convite}`; senha mínima 10). Sem login, todas as rotas (exceto `/lab/*` em DEV) mostram Entrar. Logado sem provedor (`tem_provedor=false`) → onboarding **"Conecte sua primeira API"** (reusa o cartão de provedor); dá para pular para Configurações, mas o aviso continua na Home. Rodapé da conta com o nome real e **Sair** (`POST /v1/auth/sair`; desktop apaga do cofre). Configurações → Conta → "Apagar todos os dados" continua só local, e "Apagar conta" usa `DELETE /v1/conta {senha}`.
5. **Modelos de IA** (`state/modelos.ts` vira cache do backend; nada de chave guardada):
   - Tipos do backend: `groq, openai, anthropic, google, openrouter, compativel_openai, ollama`. Cartões do app: OpenAI→`openai`; Anthropic→`anthropic`; Gemini→`google`; OpenRouter→`openrouter`; Ollama→`ollama`; Compatível→`compativel_openai`; **Groq** novo cartão→`groq`; xAI/DeepSeek/Mistral→`compativel_openai` com `base_url` pré-preenchida (`https://api.x.ai/v1`, `https://api.deepseek.com/v1`, `https://api.mistral.ai/v1`).
   - "Testar e conectar" = `POST /v1/provedores` (o backend testa antes de salvar). Mostrar a mensagem do 422/409/429 como veio. Trocar chave = `PATCH {chave}`. Desconectar = `DELETE`. Teto mensal = `PATCH {teto_mensal_usd}` (null remove). Mostrar `…` + `chave_final` e `gasto_mes_usd`.
   - Lista de modelos vem de `GET /v1/modelos` (nível N1/N2/N3/especial e ativo editáveis via `PATCH /v1/modelos/{id}`). Prioridade do usuário via `PATCH /v1/preferencias {prioridade}` (valores do enum `Prioridade` do backend).
   - Escolhas de modelo padrão (Sora, novos agentes, por agente) podem continuar no `localStorage` (não são segredo), mas só oferecem modelos ativos vindos do backend.
   - **Migração:** ao carregar, se existir `sora.modelos.v1`, apagar as chaves dele (reescrever sem `chave`/`status`, ou remover a entrada) — nenhuma chave antiga pode sobrar no navegador. Remover `testarConexao` simulado e `mascararChave` de chave completa.
6. **Backend (ferramenta de dev, sem mudar regra de produção):** comando para criar convite, ex. `uv run python -m app.cli convite criar [--codigo X] [--usos N]`; `backend/README.md` com o passo a passo de rodar local (Postgres/Redis do `infra/docker-compose.yml`, `alembic upgrade head`, `AMBIENTE=desenvolvimento SORA_MODELO_FALSO=1 uvicorn app.main:app --port 8000`). Cookie de renovação precisa funcionar pelo proxy do Vite em `http://localhost:5173`.
7. **QA continua funcionando:** `qa/e2e.mjs`, `qa/ilha.mjs`, `qa/shoot.mjs` e `npm run test:visual` passam a entrar com uma conta de teste antes (helper `qa/entrar.mjs`, credenciais por env `SORA_QA_EMAIL`/`SORA_QA_SENHA`, criando a conta com convite se faltar). Testes Vitest mockam o `fetch` — nenhum teste unitário fala com rede.

## Divisão (cada um só nos seus arquivos; precisou de arquivo de outro → pedir ao dono)

| Quem | Arquivos |
| --- | --- |
| **Tecelã** (Claude Code) | `src/api/**`, `src/state/sessao.ts`, telas Entrar/Cadastro/Onboarding (`src/screens/Entrar.tsx`, `src/components/sessao/**`), `App.tsx`/rotas/gate, rodapé da conta (`components/layout/Sidebar.tsx` só o rodapé), `vite.config.ts` (proxy), `qa/entrar.mjs` e ajustes de login em `qa/*.mjs` e testes visuais, testes em `src/api/__tests__`, `src/state/__tests__/sessao*` |
| **Lastro** (Codex) | `src/state/modelos.ts`, `components/settings/**`, `screens/Configuracoes.tsx` (aba Modelos e Conta), `components/builder/AgentConfigForm.tsx`, `EditarAgenteModal.tsx`, `builder/types.ts`, `screens/CriarAgente.tsx`, `components/projetos/*` que usam modelos, testes deles. Usa o cliente da Tecelã (`api/cliente.ts`) — combinar a interface com ela no início |
| **Âncora** (Codex) | `src-tauri/**` (keyring, comandos, capabilities, CSP), `src/desktop/ponte.ts` (só as funções do cofre), `backend/app/cli*`, `backend/README.md`, testes do CLI |
| **Lince** (Hermes + Claude Sonnet, validador) | não edita produção; roda tudo, testa no navegador e no Tauri real e reporta |

## Pronto quando

- Backend: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` (com Docker) verdes.
- App: `npm run build`, `npx oxlint`, `npm test` verdes; `node qa/e2e.mjs` e `node qa/ilha.mjs` verdes com o backend local rodando.
- Desktop: `cargo clippy -- -D warnings`; login no Tauri real guarda a renovação no Credential Manager e sobrevive a fechar/abrir.
- Fluxo real: criar conta com convite → onboarding → conectar um provedor falso compatível com OpenAI (servidor local com `/v1/models`, permitido só em desenvolvimento) → modelos aparecem → trocar nível → desconectar. Chave inválida mostra o 422 em PT-BR.
- `grep` no `localStorage` (DevTools) e no código: **nenhuma chave de API** no navegador.

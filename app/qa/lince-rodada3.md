VEREDITO: APROVADO

Lince — rodada 3 da etapa 2 (2026-10-17)

T1, T2 e L1 foram corrigidos e passaram nos repros focados e no fluxo real completo. Nenhum achado novo para Tecelã, Âncora ou Lastro.

## Repros focados no navegador real — 390 × 844

Com backend, Vite e provedor falso reais, conta nova e sessão real:

- T1 — APROVADO: o BottomSheet móvel mostrou identidade da conta, link Configurações e botão Sair; Configurações navegou para `/configuracoes`; Sair encerrou a sessão. O botão Sair mediu 44 px de altura. Implementação: `app/src/components/layout/AppShell.tsx:82-85` e `app/src/components/layout/Sidebar.tsx:153-176`.
- T2 — APROVADO: o onboarding mostrou Sair diretamente; o botão mediu 44 px e encerrou a sessão, voltando para Entrar. Implementação: `app/src/components/sessao/Onboarding.tsx:25-29,39-42`.
- L1 — APROVADO: o cartão mostrou exatamente `lince-grande`, `lince-medio` e `lince-pequeno`; os padrões mostraram `Compatível com OpenAI · lince-*`; nenhum texto exibiu `openai/`. Implementação: `app/src/state/modelos.ts:34-42`, `app/src/components/settings/ProviderCard.tsx:70-74` e `app/src/components/settings/ModelDefaults.tsx:14-18`.
- Resultado: `node qa/lince-r3-repros.mjs` — 12/12.
- Console: sem erros inesperados; um 401 esperado ocorreu ao encerrar a sessão.
- Evidências: `app/qa/shots/lince/rodada3/t1-menu-conta-390.png`, `t2-onboarding-sair-390.png` e `l1-modelos-amigaveis-390.png`.

## Fluxos reais e E2E

- `node qa/lince-fluxo-real.mjs 1440` — 25/25.
- `node qa/lince-fluxo-real.mjs 390` — 26/26.
- O primeiro reteste móvel encontrou somente uma suposição antiga do script do Lince: ele detectava o novo Sair direto, mas ainda tentava abrir o menu de conta antigo. `qa/lince-fluxo-real.mjs` foi ajustado para clicar o Sair direto e o fluxo completo passou; não era defeito do produto.
- Ambos os fluxos confirmaram: convite inválido em PT-BR; onboarding; chave inválida → 422 `O provedor recusou a chave.`; conexão; três modelos; nível/ativo/teto/prioridade persistentes; somente modelos ativos nos padrões; desconexão/reconexão; sair/entrar; renovação httpOnly; respostas sem chave; console sem erro inesperado.
- `node qa/e2e.mjs` — aprovado: 13 screenshots, sem erros de console.
- `node qa/ilha.mjs` — aprovado: fluxo completo, filtro de agentes, 7 screenshots em 1440 × 900 e 390 × 844, console limpo.

## Portões canônicos

### App

- `npm run build` — aprovado; 187 módulos transformados. Há apenas o aviso já conhecido de chunk principal maior que 500 kB.
- `npx oxlint` — aprovado, zero erros.
- `npm test` — 13 arquivos e 119 testes aprovados.

### Backend

Executado sem herdar as variáveis do servidor local, para que `tests/conftest.py` instalasse o ambiente canônico:

- `uv run ruff check .` — aprovado.
- `uv run ruff format --check .` — 237 arquivos já formatados.
- `uv run pytest -q` — 912 aprovados, 3 ignorados, 5 avisos. Os ignorados continuam sendo 2 testes de symlink sem permissão no Windows e 1 teste opcional sem `playwright.async_api` no ambiente do backend.

## Segurança da chave de API

- Nos fluxos 1440 e 390, a chave completa não apareceu no DOM, localStorage, sessionStorage, IndexedDB nem em respostas do backend.
- localStorage observado: somente `sora.projetos.v1`; sessionStorage: somente `sora.chegou`; IndexedDB vazio.
- A chave trafegou somente no corpo esperado de `POST /v1/provedores`.
- O cookie `sora_renovacao` permaneceu httpOnly, path `/v1/auth`, SameSite Lax.
- Busca em `app/src` não encontrou persistência de chave/token/senha em localStorage ou sessionStorage. `app/src/state/modelos.ts:100-120,145-153` persiste somente escolhas de modelos; `app/src/api/cliente.ts:54-70,144-162` mantém acesso em memória e usa o cofre apenas no desktop.
- Literais que parecem chave aparecem somente no teste de migração de estado legado. Não há segredo real no código de produção.
- `node qa/lince-legado.mjs` — aprovado: removeu a chave do formato legado e regravou `sora.modelos.v1` versão 2 somente com preferências não secretas.

## Encerramento

Encerrados ao final, conforme pedido:

- Vite — PID 1136, porta 5173.
- Backend/Uvicorn — PID 25592, porta 8000.
- Provedor falso — PID 24020, porta 8765.

Verificação posterior: os três PIDs não existem mais, nenhuma das três portas está em `LISTENING` e os três health checks retornaram offline (`HTTP 000`). Também removi do Redis a janela de rate limit criada pelos cadastros do Lince e apaguei o convite temporário do scratch.

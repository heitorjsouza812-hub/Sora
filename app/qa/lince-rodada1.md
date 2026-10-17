# Lince — rodada 1 da etapa 2 (2026-10-17)

Veredito: NÃO APROVADO. O fluxo funcional principal passou, mas há 2 achados médios da Tecelã no acesso à conta/sessão e 1 achado baixo do Lastro.

## Verificações

| Item | Resultado |
| --- | --- |
| app `npm run build`, `npx oxlint`, `npm test` | OK; oxlint 0; 114 testes / 11 arquivos |
| backend `ruff check`, `ruff format --check`, `pytest -q` (Docker) | OK; 237 arquivos formatados; 912 passed, 3 skipped (2 symlink, 1 playwright ausente) |
| Tauri real | Fora desta rodada por instrução; fica para a rodada 2 |
| `qa/e2e.mjs`, `qa/ilha.mjs` (logados, backend local) | aprovados, console limpo |
| Fluxo real `qa/lince-fluxo-real.mjs` 1440 px | 25/25 |
| Fluxo real 390 px | 25/26 (a falha é o achado T1) |
| Chave de API no navegador | nenhuma: localStorage só `sora.projetos.v1`; sessionStorage só chaves de UI; IndexedDB vazio; cookie `sora_renovacao` httpOnly path `/v1/auth`; migração do legado (`qa/lince-legado.mjs`) remove chaves antigas de `sora.modelos.v1` |
| Chave nas respostas do backend | nenhuma (campos: id, tipo, base_url, chave_final, teto_mensal_usd, gasto_mes_usd, modelos…); a chave só viaja em `POST /v1/provedores` |
| Chave no código | só marcadores falsos (sk-TES…7890) |
| Renovação ao recarregar (`qa/lince-renovacao.mjs`) | OK: 4 recarregamentos, rota profunda, 17 s depois, duas abas juntas + 17 s depois |

Nota de ambiente: uma primeira execução do pytest herdou as variáveis locais usadas para subir o Uvicorn e falhou em 11 testes de configuração. O comando foi repetido com essas variáveis removidas, permitindo que `tests/conftest.py:14-20` instalasse os valores canônicos; o resultado final foi 912/912. Isso não é achado do produto.

## Achados por dono

### Tecelã
- T1 [MÉDIO] Celular 390 px logado: o menu ☰ (`app/src/components/layout/AppShell.tsx:82-84`, só `Navegacao`) não tem conta, Configurações nem Sair; a conta só existe em `app/src/components/layout/Sidebar.tsx:161-174`, oculta no celular. Repro: `node qa/lince-fluxo-real.mjs 390` (25/26; falha "dá para Sair"), screenshot `app/qa/shots/lince/390/10-menu-mobile.png`.
- T2 [MÉDIO] `app/src/components/sessao/Onboarding.tsx:16-35`: sem Sair nem menu da conta; quem entrou na conta errada precisa usar "Fazer isso depois em Configurações" antes de alcançar a conta. Repro: entrar com qualquer conta sem provedor.
- INFO de operação: `POST /v1/auth/cadastrar` limita 5/h por IP. Para repetir a bateria local, foi removida apenas a chave de teste `limite:cadastro:ip:127.0.0.1` no Redis; o fluxo passou depois disso.

### Lastro
- L1 [BAIXO] O nome do modelo aparece com prefixo técnico do LiteLLM: `openai/lince-grande`, `openai/lince-medio` e `openai/lince-pequeno` (`app/src/components/settings/ProviderCard.tsx:69-76`; `app/src/components/settings/ModelDefaults.tsx:15-22`). Repro: conectar o provedor falso e abrir Configurações → Modelos de IA. Screenshot: `app/qa/shots/lince/1440/08-config-recarregado.png`.
- Tudo mais do fluxo passou: modelos aparecem, nível N2→N3 e ativo persistem, teto 7,50 persiste, prioridade persiste, padrão da Sora só lista modelos ativos, desconectar/reconectar e chave errada → 422 `O provedor recusou a chave.` em PT-BR.

### Âncora
- Nenhum achado no escopo web/CLI desta rodada. Tauri/Credential Manager fica para a rodada 2 por instrução.

## Serviços deixados ligados

- Vite: porta 5173, listener PID 1136.
- Uvicorn: porta 8000, listener PID 25592.
- Provedor falso do Lince: porta 8765, listener PID 24020.

Arquivos do Lince: `qa/lince-fluxo-real.mjs` (import sem uso corrigido), `lince-provedor-falso.mjs`, `lince-legado.mjs`, `lince-renovacao.mjs`, `lince-tauri.mjs`, `lince-linha-de-base.md`, este relatório.

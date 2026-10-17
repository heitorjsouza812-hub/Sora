# Lince — rodada 2 da etapa 2: Tauri real (2026-10-17)

Veredito do Tauri: **APROVADO**. Nenhum achado novo para a Âncora, Tecelã ou Lastro no escopo desktop desta rodada.

## Execução real

- Comando: `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333 npm run desktop`.
- Binário real: `app/src-tauri/target/debug/sora.exe`.
- CDP WebView2: Edge 155, porta 9333, alvos `main` e `ilha` presentes.
- O Tauri foi fechado ao final; não há `sora.exe` nem listener em 9333.
- Serviços preservados: Vite em `127.0.0.1:5173` (PID 1136) e backend em `127.0.0.1:8000` (PID 25592), ambos HTTP 200 após o fechamento.

## Login e cofre do Windows

1. Estado inicial sem credencial: tela `Entrar na Sora`; `cmdkey /list` sem alvo da Sora.
2. Login real com a conta QA: `POST /v1/auth/entrar` respondeu 200 e abriu `Conta, conecte sua primeira API`.
3. Credential Manager passou a listar `LegacyGeneric:target=token-renovacao.com.sora.desktop`.
4. No WebView principal, `localStorage` tinha somente `sora.projetos.v1` e `sora.painel.projeto`; `sessionStorage`, somente `sora.chegou`. Nenhum campo de token, JWT, senha QA ou cookie legível por JavaScript.
5. O processo `sora.exe` foi encerrado completamente; a credencial permaneceu no Credential Manager.
6. Após reabrir o Tauri, a tela abriu logada e o reload observou `POST /v1/auth/renovar` HTTP 200. O armazenamento do navegador continuou sem tokens.
7. `Sair` pela UI respondeu `POST /v1/auth/sair` HTTP 204, voltou para `Entrar na Sora` e removeu a entrada do Credential Manager. Conferência final: alvo ausente.

Implementação correspondente: token de acesso apenas em memória e renovação no cofre em `app/src/api/cliente.ts:116-148`; ponte do cofre restrita à janela principal em `app/src/desktop/ponte.ts:88-103`; keyring do Windows em `app/src-tauri/src/lib.rs:185-225`.

## Isolamento da janela da ilha

Provas dinâmicas feitas diretamente no alvo CDP `index.html?janela=ilha`:

- `cofre_ler`: negado — `not allowed on window "ilha"`;
- `cofre_gravar`: negado — `not allowed on window "ilha"`;
- `cofre_apagar`: negado — `not allowed on window "ilha"`;
- a credencial permaneceu existente depois das três tentativas.

A capability `main` contém as três permissões do cofre (`app/src-tauri/capabilities/main.json:5-13`), enquanto a capability `ilha` não contém nenhuma (`app/src-tauri/capabilities/ilha.json:5-12`). O Rust ainda aplica uma segunda trava por label em `app/src-tauri/src/lib.rs:149-163` e `190-225`.

## CSP e qualidade

- Recarreguei `main` e `ilha` com listeners de console/pageerror ativos: zero erros de console e zero erros de CSP.
- `devCsp` permite apenas os endpoints de desenvolvimento necessários em `app/src-tauri/tauri.conf.json:14-16`.
- `cargo test`: 4/4 testes passaram, incluindo `cada_comando_so_na_sua_janela` e `capabilities_batem_com_a_tabela`.
- `cargo clippy -- -D warnings`: verde.
- `node --check qa/lince-tauri-r2.mjs` e `npx oxlint qa/lince-tauri-r2.mjs`: verdes.

## Evidências

- Script: `app/qa/lince-tauri-r2.mjs`.
- Screenshots: `app/qa/shots/lince/tauri-r2-entrou.png`, `tauri-r2-reabriu.png`, `tauri-r2-saiu.png`.
- T1, T2 e L1 não foram reavaliados nesta execução; aguardam o aviso de conclusão da Tecelã/Âncora, como combinado.

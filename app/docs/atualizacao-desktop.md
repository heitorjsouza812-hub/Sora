# Atualização automática do app de desktop

Onda 1, 2026-11-20. Ideia vista no OpenBot (`docs/referencias/openbot-comparativo.md`), feita do
zero com o plugin oficial de atualização do Tauri.

## Como funciona

- Ao abrir (15 s depois) e a cada 6 horas, a janela principal pergunta ao Rust
  (`atualizacao_verificar`, `src-tauri/src/atualizacao.rs`) se há versão nova.
- O Rust lê `latest.json` no endereço de `plugins.updater.endpoints` (`tauri.conf.json`): hoje,
  `https://github.com/heitorjsouza812-hub/Sora/releases/latest/download/latest.json`.
- Achou versão nova: aparece o aviso "A versão X da Sora está pronta." com **Instalar e reiniciar**
  (uma vez por versão). Também dá para procurar e instalar em Configurações → Conta → Versão do app.
- **Instalar** baixa o instalador e só instala se a assinatura (minisign) bater com a chave pública
  de `plugins.updater.pubkey`. Assinatura errada: nada é instalado e o app avisa. No Windows o
  instalador (modo `passive`) fecha o app e abre a versão nova.
- Só a janela principal pode verificar e instalar (`COMANDOS_POR_JANELA` e
  `capabilities/main.json`). No navegador e na Ilha nada disso roda.

## Hoje está desligado

`plugins.updater.pubkey` está vazio. Assim o app mostra "Esta versão ainda não se atualiza sozinha"
e não faz pedido nenhum. Para ligar, alguém do time precisa criar o par de chaves de assinatura
(passo 1). **A chave privada é segredo**: não vai para o repositório, nem para documento, nem
para conversa.

## Como ligar

1. Gerar as chaves, no PC de quem cuida das versões (pede uma senha):

   ```powershell
   cd app
   npx tauri signer generate -w "$env:USERPROFILE\.tauri\sora-atualizacao.key"
   ```

   Saem dois arquivos: `sora-atualizacao.key` (privada, segredo) e `sora-atualizacao.key.pub`
   (pública).
2. Copiar o conteúdo do `.pub` para `plugins.updater.pubkey` em `app/src-tauri/tauri.conf.json`
   e fazer commit (a chave pública não é segredo).
3. No GitHub, em Settings → Secrets and variables → Actions, criar:
   - `TAURI_SIGNING_PRIVATE_KEY`: o conteúdo do arquivo `.key`;
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: a senha do passo 1.
4. Para lançar uma versão: subir `version` em `tauri.conf.json` e `Cargo.toml` (as duas iguais),
   juntar na `main` e enviar a tag:

   ```powershell
   git tag desktop-v0.2.0
   git push origin desktop-v0.2.0
   ```

   O fluxo `.github/workflows/desktop-versao.yml` gera o instalador, os `.sig` e o `latest.json` e
   cria a versão como **rascunho**. Conferir e publicar o rascunho: só então os apps instalados
   enxergam a versão nova.
5. O repositório precisa ser público para o endereço `releases/latest/download` funcionar sem
   login. Se ele continuar privado, trocar `plugins.updater.endpoints` por um endereço público
   (por exemplo, o domínio da Sora servindo o `latest.json`).

## Cuidados

- Perder a chave privada = os apps já instalados não aceitam mais nenhuma atualização (é preciso
  reinstalar à mão). Guardar uma cópia no cofre de senhas do time.
- Trocar a chave pública exige uma versão intermediária assinada com a chave antiga.
- O instalador do Windows continua sem assinatura de código (o SmartScreen pode avisar). Isso é
  outro item: "Instalador assinado" em `CLAUDE.md` §7.5.

# Desktop da Sora

## API de produção na CSP

Antes de gerar um instalador de produção, substitua `https://api.seu-dominio.com.br` em
`tauri.conf.json` pela origem HTTPS exata configurada em `VITE_API_URL`. Mantenha a origem sem
caminho e não use curingas. O `devCsp` já libera `http://localhost:8000` para o backend local.

O token de renovação do desktop é armazenado no Credential Manager do Windows pelo crate
`keyring`, sob o serviço `com.sora.desktop`. Somente a janela `main` recebe as capabilities dos
comandos `cofre_ler`, `cofre_gravar` e `cofre_apagar`.

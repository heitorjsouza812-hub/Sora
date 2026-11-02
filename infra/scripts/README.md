# Backups

Scripts para backup diário cifrado do PostgreSQL, cópia semanal dos anexos e
teste mensal de restauração, conforme a seção 8.3. Exigem `age` e AWS CLI.

## Prova da cerca do navegador

Com Docker Desktop rodando, execute `sh scripts/provar-isolamento-navegador.sh` a partir de
`infra/`. A prova nasce dentro do contêiner `navegador`: `postgres`, `redis`, o endpoint de
metadados `169.254.169.254` e um nome resolvido para IP privado falham por HTTP e WebSocket;
`https://example.com/` precisa funcionar pelo proxy de saída.


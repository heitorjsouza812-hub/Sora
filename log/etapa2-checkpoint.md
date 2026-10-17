# Etapa 2 — checkpoint do loop

_Se o trabalho parar (cota acabou), retome daqui. Especificação: `log/etapa2-app-provedores.md`._

## Estado em 2026-10-17 (início do loop)

- `main` = GitHub (`b31420e`, merge etapa 1 + Rakazo). Etapa 2 inteira está **sem commit** na árvore de trabalho.
- Código escrito: cliente HTTP + sessão + Entrar/Onboarding/gate (Tecelã), Modelos de IA (Lastro), cofre Tauri + CLI de convite + README (Âncora), login nos scripts de QA (`qa/entrar.mjs`).
- Verde agora: backend ruff + pytest 912 passed / 3 skipped; app tsc, 112 testes, build; oxlint com 1 aviso (`qa/lince-fluxo-real.mjs` import sem uso).
- Falta: validação de ponta a ponta (fluxo real com backend local, QA e2e/ilha, Tauri com Credential Manager, nenhuma chave no navegador), corrigir achados, commit.

## Time (Maestri)

- Lince (Hermes + GPT, validador) · Tecelã (Codex, sessão/QA) · Âncora (Codex, Tauri/CLI) · Lastro (Codex, Modelos — sob demanda). Orquestrador: Claude Code.
- Prioridade de cota: Codex. Claude com pouca cota.

## Rodadas

<!-- o orquestrador acrescenta uma linha por rodada -->
- **Rodada 1 (disparada):** Tecelã confere regras 1/3/4/7 e testes; Âncora confere regras 2/6, clippy, CLI; Lince sobe backend+vite e valida o fluxo real no navegador + e2e/ilha + busca de chaves. Tauri real fica para a rodada 2. Processos antigos (vite 5173, uvicorn 8000) encerrados antes.
  - Tecelã ✅: regras 1/3/4/7 conferidas; corrigiu `api/cliente.ts` (falha da renovação após 401 por rede/5xx agora encerra a sessão) + 2 testes. App build/oxlint/114 testes verdes.
  - Âncora ✅: regras 2/6 já completas, sem edição. clippy, cargo test (4), ruff, test_cli (5) verdes. Pendência de produção (não bloqueia a etapa): trocar `https://api.seu-dominio.com.br` no CSP do `tauri.conf.json` pela origem definitiva da API antes do instalador final.
  - Lince ❌ (`app/qa/lince-rodada1.md`): fluxo 1440 px 25/25, renovação/recarregar/duas abas, e2e, ilha, 912 + 114 testes verdes, nenhuma chave no navegador. Achados: **T1** menu móvel (AppShell.tsx:82-84) sem Configurações/conta/Sair; **T2** Onboarding sem Sair; **L1** prefixo `openai/` no nome dos modelos (ProviderCard/ModelDefaults).
- **Rodada 2 (disparada):** Tecelã corrige T1/T2 (AppShell autorizado); Âncora cobre L1 no lugar do Lastro; Lince testa o Tauri real (Credential Manager, fechar/abrir, Sair apaga, ilha sem acesso ao cofre, CSP). Depois: Lince reconfere T1/T2/L1 → se aprovado, commit.
  - Tecelã ✅ T1/T2: `ContaRodape` compartilhado (Sidebar.tsx) no BottomSheet do AppShell; Sair no Onboarding; alvos de 44 px em sora.css; teste `layout/__tests__/acessoConta.test.tsx`. Build/oxlint/119 testes verdes.
  - Lince ✅ Tauri real (`app/qa/lince-rodada2-tauri.md`): renovação no Credential Manager, sobrevive a fechar/abrir, Sair apaga, ilha negada nos 3 comandos do cofre, zero erros de CSP.
  - ⚠️ Licença do Maestri: o teste acabou e os recrutas não conseguem mais responder com `maestri ask`. Combinado com o Lince: ele grava o veredito em `app/qa/lince-rodada3.md`.
- **Rodada 3 — APROVADO** (`app/qa/lince-rodada3.md`). Etapa 2 concluída e commitada.
- Rodada 3 (pedido): Lince reconfere T1/T2/L1 + fluxo completo + e2e/ilha + todas as checagens, depois encerra vite/backend/provedor falso. Aprovado → commit da etapa 2.
  - Âncora ✅ L1: `nomeAmigavelDoModelo` em state/modelos.ts (usa `nome_exibicao` ou tira o prefixo `tipo/` só na tela; id completo salvo); teste `settings/__tests__/modelos-amigaveis.test.tsx`. Build/oxlint/119 testes verdes.

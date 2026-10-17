# Log do projeto Sora

Esta pasta registra **o que foi feito** e **onde paramos**, para qualquer integrante (ou IA) retomar sem precisar ler a conversa inteira.

| Arquivo | Para que serve |
|---|---|
| [`ONDE-PARAMOS.md`](ONDE-PARAMOS.md) | **Leia primeiro.** Estado atual, o que está pendente e o próximo passo. |
| [`2026-10-10.md`](2026-10-10.md) | Diário do dia 10/10/2026: tudo que foi construído, em ordem, com os commits. |
| [`2026-10-11.md`](2026-10-11.md) | Revisão do front-end contra a especificação do backend: o que adicionar e consertar. |
| [`2026-10-14.md`](2026-10-14.md) | Decisão de fazer os agentes em LangChain (plano versão 2.1). |
| [`2026-10-15.md`](2026-10-15.md) | Fundação do backend da fase 1 e revisão de segurança. |
| [`2026-10-17.md`](2026-10-17.md) | Peças do Rakazo portadas para o backend (fases 1, 2 e 3). |

## Como registrar uma nova sessão

1. Crie `log/AAAA-MM-DD.md` com: quem trabalhou, o que fez (com os commits), decisões tomadas e o que ficou pendente.
2. Atualize o `ONDE-PARAMOS.md`, que deve sempre refletir o estado mais recente.
3. Se mudou algo de produto, atualize também o `CLAUDE.md` (§7) e copie para o `AGENTS.md`.

Detalhes técnicos (como rodar, estrutura de pastas, decisões de produto) ficam no [`CLAUDE.md`](../CLAUDE.md), §7.

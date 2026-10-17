# prompts

Um arquivo por prompt, com versão no nome (`{nome}.v{n}.md`). O texto é cópia
exata dos blocos de `docs/plano-de-implementacao/03-prompts.md` (versão 2).
Mudou o prompt: crie a versão seguinte (`.v2.md`), troque em
`app/agentes/prompts.py` (`VERSOES`) e rode a avaliação (§8.5).

| Arquivo | Prompt | Quem usa |
| --- | --- | --- |
| `sora_base.v1.md` | Prompt base da Sora | Sora e agentes individuais |
| `sistema1.v1.md` | Sistema 1: triagem e roteamento | `app/sistema1` |
| `planejador.v1.md` | Planejador da cadeia | `app/orquestrador/planejador.py` |
| `especialista_comum.v1.md` | Modelo comum dos especialistas | especialistas (`{trecho_do_papel}`) |
| `especialista_pesquisador.v1.md` | Trecho do Pesquisador | |
| `especialista_redator.v1.md` | Trecho do Redator | |
| `especialista_designer.v1.md` | Trecho do Designer (só com modelo de imagem) | |
| `perfil_agente.v1.md` | Perfil de agente a partir do pedido | Agente independente e construtor |
| `verificador.v1.md` | Verificador | `app/orquestrador/verificador.py` |
| `revisor_acoes.v1.md` | Revisor de ações | `app/revisor` |
| `memoria_sintese.v1.md` / `memoria_verificacao.v1.md` | Memória (fase 2) | `app/memoria` |
| `lembrete_inicio_turno.v1.md`, `lembrete_silencio.v1.md`, `lembrete_entrega.v1.md` | Lembretes automáticos | `agentes/middleware/lembretes.py` |
| `cerca_dado_externo.v1.md` | Cerca `<dado_externo>` | `agentes/prompts.py` (`cercar`) |
| `aviso_dado_externo.v1.md` | Trecho sobre `<dado_externo>` que vai no prompt de todo agente | montagem dos agentes |
| `juiz_rapido.v1.md` | Instrução de sistema do revisor rodando como juiz rápido (JSON estrito) | `app/revisor/juiz.py` |
| `compactacao_historico.v1.md` | Resumo cumulativo da conversa | `app/memoria/compactacao.py` |

Os dois últimos vieram do Rakazo (`docs/referencias/rakazo.md`) e ainda não estão no `03-prompts.md`.

Atenção: vários prompts têm JSON com `{ }` literais. O preenchimento troca só
as chaves conhecidas (`{pedido}`, `{perfil_do_agente}`…), nunca `str.format`.

Dono: Trama (Pessoa 3); o conteúdo é da equipe toda.

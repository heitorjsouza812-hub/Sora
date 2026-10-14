# orquestrador

Cadeias da Sora: estados, planejador, verificador, entregas e versões.
Especificação: §6 (execução), §1 (`cadeias`, `etapas`, `entregas`) e §3.2.

| Arquivo | O que faz |
| --- | --- |
| `estados.py` | `StatusCadeia`, `StatusEtapa`, transições e status do agente no app |
| `cadeia.py` | Criar cadeia, pegar etapa sem trabalho em dobro, etapas prontas, limites, progresso, cancelar |
| `planejador.py` | Esquema do plano (`Plano`, `EtapaPlano`, `PerguntaPlano`), validação e gravação |
| `verificador.py` | Roda o Verificador e aplica a regra de reprovação |
| `entregas.py` | Entregas por versão, comparação e aprovação |
| `ajuste.py` | "Pedir ajuste": cadeia `versao + 1` com o especialista certo |

Quem chama: os jobs em `backend/workers/`. Dono: Trama (Pessoa 3).

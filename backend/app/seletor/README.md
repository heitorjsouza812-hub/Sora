# app/seletor

Seletor de modelo (especificação §5). Dona: Bússola.

| Módulo | Responsabilidade |
| --- | --- |
| `tipos.py` | `Nivel`, `Capacidade`, `Prioridade`, `PapelModelo`, `ModeloCandidato`, `ContextoSeletor` |
| `politica.py` | carrega `config/politica.yaml` (papéis, dificuldade → nível, limites) |
| `catalogo.py` | carrega `config/catalogo_modelos.yaml`, cruza modelos do provedor com o catálogo |
| `flags.py` | carrega `config/flags.yaml` (Laya, dados de treino, revisor de ações) |
| `seletor.py` | `escolher_modelos` → `ResultadoSelecao` (lista ordenada + avisos para a linha do tempo) |

O seletor é função pura: não acessa banco nem Redis. Quem chama monta o `ContextoSeletor`
(modelos ativos, provedores com pausa e gasto do mês, prioridade, conversa privada).

Diferença para o esqueleto da §5: `escolher_modelos` devolve `ResultadoSelecao` (`.modelos` +
`.avisos`) em vez de só a lista, porque a especificação manda marcar na linha do tempo quando o
nível sobe, quando usa o mais forte e quando o verificador roda no mesmo modelo.

Estado: esqueleto (etapa 1). Os corpos levantam `NotImplementedError`.

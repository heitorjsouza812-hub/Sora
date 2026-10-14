# busca

Busca na web e leitura de páginas (especificação §8.1).

| Arquivo | O que faz |
| --- | --- |
| `provedor.py` | `ResultadoBusca`, `ProvedorBusca` (Protocol), `obter_provedor()`, cache e limites |
| `tavily.py` / `brave.py` | Provedores da fase 1 (a equipe escolhe um), chave da equipe só no servidor |
| `searxng.py` | Só desenvolvimento local (`--profile dev`) |
| `falso.py` | Resultados fixos, sem rede: testes e modelo falso |
| `ler_pagina.py` | Download seguro (bloqueio de IP interno em cada redirecionamento), extração e cache |

As ferramentas `buscar_web` e `ler_pagina` (em `app/ferramentas/`) usam este
pacote e cercam o resultado com `<dado_externo>`. Dono: Trama (Pessoa 3).

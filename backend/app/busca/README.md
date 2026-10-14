# busca

Busca na web e leitura de páginas (especificação §8.1).

| Arquivo | O que faz |
| --- | --- |
| `provedor.py` | `ResultadoBusca`, `ProvedorBusca` (Protocol), `obter_provedor()`, `buscar()` (limites → cache → provedor), erros |
| `tavily.py` / `brave.py` | Provedores da fase 1 (a equipe escolhe um), chave da equipe só no servidor |
| `searxng.py` | Só desenvolvimento local (`--profile dev`) |
| `falso.py` | Resultados fixos, sem rede: testes e modelo falso |
| `ler_pagina.py` | Download seguro, extração (HTML, PDF, texto) e cache |

## Busca

- Entrada única: `buscar(redis, provedor, nome, consulta, usuario_id=, cadeia_id=)`.
- Limites: 300 buscas por usuário por dia (dia em UTC) e 20 por cadeia. Contam
  todo pedido, inclusive os respondidos pelo cache. Ao passar: `LimiteDeBusca`,
  com mensagem para o Pesquisador seguir com o que já tem.
- Cache de 24 h por provedor + idioma + limite + consulta normalizada.
- `ResultadoBusca.origem` é o domínio do resultado (sem `www.`).
- Erros do provedor viram `ErroBusca` com mensagem clara; a chave nunca aparece
  em mensagem, `repr` ou log.

## Ler página (SSRF)

- Só `http`/`https`, sem usuário e senha na URL.
- Cada destino (o inicial e cada `Location`, até 5) é resolvido e recusado se
  **qualquer** IP não for público: loopback, redes privadas, CGNAT, link-local
  (metadados `169.254.169.254`), ULA (`fd00:ec2::254`), multicast, reservados e
  IPv4 escondido em IPv6 (mapeado, 6to4, NAT64, Teredo).
- `BackendSeguro`: a camada de rede do httpx resolve de novo, confere e conecta
  no IP conferido (fecha o DNS rebinding); o TLS usa o nome original.
- 10 s no total, até 5 MB (pelo `Content-Length` e durante o download), sem
  proxy do ambiente.
- Extração: `trafilatura` (HTML), `pypdf` (PDF) e texto puro; outros tipos são
  recusados. Cache de 24 h por URL.

As ferramentas `buscar_web` e `ler_pagina` (em `app/ferramentas/`) usam este
pacote e cercam o resultado com `<dado_externo>`. Dono: Trama (Pessoa 3).

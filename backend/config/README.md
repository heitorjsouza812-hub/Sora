# backend/config

Arquivos de configuração do seletor e das flags. Dona: Bússola.

| Arquivo | Seção da especificação | Lido por |
| --- | --- | --- |
| `politica.yaml` | §5 "Arquivo politica.yaml" (papéis, dificuldade → nível, limites) | `app/seletor/politica.py` |
| `catalogo_modelos.yaml` | §5 "Catálogo de modelos" (nível, preço, capacidades) | `app/seletor/catalogo.py` |
| `flags.yaml` | §7 (Laya), plano 01 (flags) | `app/seletor/flags.py` |

- O catálogo é revisto todo mês (preços mudam). O nível é só uma proposta até o modelo passar no
  "Teste dos modelos" (§5). As capacidades e os contextos que a especificação não diz estão como
  proposta/nulos: veja o cabeçalho do arquivo.
- `SORA_CONFIG_DIR` muda a pasta onde os YAMLs são procurados (padrão: esta pasta).
- Sem chave, token ou senha aqui.

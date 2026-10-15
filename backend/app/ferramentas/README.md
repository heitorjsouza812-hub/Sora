# ferramentas

Ferramentas dos agentes (especificação §4), uma por arquivo: o esquema
Pydantic dos argumentos e a função `async` que executa. Viram `@tool` do
LangChain em `registro.py` (§6.1).

| Arquivo | O que tem |
| --- | --- |
| `base.py` | `ContextoFerramenta`, prazos e limite de 20.000 caracteres |
| `arquivos.py` | Caminhos seguros: `validar_nome_arquivo` (sem pastas, `..`, NUL, reservados do Windows, ponto no início) e conferência do caminho resolvido dentro da pasta da cadeia e do volume |
| `permissoes.py` | `FERRAMENTAS_POR_PAPEL`, ferramentas com revisor e com cerca |
| `rotulos.py` | Rótulos dos passos do painel Trabalho ("Buscando: …"), parâmetros sem segredos |
| `registro.py` | `ESQUEMAS` (nome → classe) e `criar_ferramentas()` |
| `falar.py`, `perguntar.py` | Sora e agentes individuais falando com o usuário |
| `disparar_especialista.py`, `ver_especialista.py`, `mensagem_especialista.py`, `parar_especialista.py` | Sora coordenando a cadeia |
| `buscar_web.py`, `ler_pagina.py`, `ler_anexo.py` | Leitura (resultado na cerca `<dado_externo>`) |
| `escrever_arquivo.py`, `gerar_imagem.py` | Redator e Designer |
| `entregar.py`, `veredito.py` | Fim da etapa de especialista e do Verificador |
| `criar_agente.py` | Cartão fixo de aprovação |

Fora da fase 1: `buscar_memoria`, `lembrar`, `enviar_para_agente` (fase 2) e
`chamar_conector`, `executar_comando`, `navegador_*` (fase 3).

Dono: Trama (Pessoa 3).

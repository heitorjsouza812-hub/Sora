"""Camada de modelos de IA da Sora (especificação §5, §6.1 e §8.4).

Tudo que fala com os provedores do usuário passa por aqui: ``ChatLiteLLM`` (LangChain + LiteLLM)
com a chave e a URL do próprio usuário, custo de cada chamada, troca de provedor em falha,
geração de imagem e o modelo falso para desenvolver (``SORA_MODELO_FALSO=1``).

Os módulos não importam o LangChain/LiteLLM na hora do ``import`` do pacote; os imports pesados
ficam dentro das funções ou em ``TYPE_CHECKING``.
"""

import os

# O LiteLLM baixa o mapa de preços da internet ao ser importado. Por padrão usamos o mapa que vem
# no pacote (reprodutível, sem rede no start nem nos testes). Quem quiser o mapa remoto define
# LITELLM_LOCAL_MODEL_COST_MAP=False no ambiente.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

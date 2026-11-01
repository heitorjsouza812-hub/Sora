"""Navegador por árvore de acessibilidade: o jeito principal de um agente da Sora ver e usar
uma página.

O agente **observa** a aba (árvore com papel, nome, valor e estados; refs ``@sXXXXXXX:eN`` nos
elementos acionáveis), **age** numa ref e **observa de novo** para conferir. Sem pixels e sem
coordenadas: a ref é reencontrada e conferida antes de cada ação, o elemento precisa estar
pronto, e a resposta diz se a ação chegou na página e se é seguro repetir.

Peças:

- ``resposta.py`` — envelope ``ok``/``dados``/``erro``, códigos, entrega e repetição;
- ``refs.py`` — leituras, refs qualificadas, perfuração por região;
- ``identidade.py`` — reencontrar a ref sem chutar (camadas + confirmação);
- ``acionabilidade.py`` — checagens antes de agir, política física/semântica;
- ``motor.py`` — ``NavegadorArvore``: observar, procurar, elemento, agir, tecla, esperar, lote;
- ``rastro.py`` — rastro redigido das chamadas;
- ``pagina.js`` — o que roda dentro da página;
- ``ferramentas.py`` — ferramentas ``navegador_*`` dos agentes e o texto para o modelo.

Adaptação do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0), que faz isso
para apps de desktop pela árvore de acessibilidade do sistema. Aqui o alvo é a página do
Chromium da Sora; o código foi escrito para a Sora, em Python e JavaScript. Veja
``docs/referencias/agent-desktop.md``.
"""

from app.navegador.arvore.acionabilidade import Politica
from app.navegador.arvore.ferramentas import ESQUEMAS, ServicoArvore, para_modelo
from app.navegador.arvore.motor import CursorAgente, NavegadorArvore
from app.navegador.arvore.resposta import Codigo, Entrega, ErroNavegador, Repetir, Resposta

__all__ = [
    "ESQUEMAS",
    "Codigo",
    "CursorAgente",
    "Entrega",
    "ErroNavegador",
    "NavegadorArvore",
    "Politica",
    "Repetir",
    "Resposta",
    "ServicoArvore",
    "para_modelo",
]

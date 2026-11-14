"""Ferramentas ``computador_*`` (C2): o bot usa o próprio computador virtual.

Política (``app/revisor/politica.py``): observar, arquivos, escrever na própria área e desligar
são ``livre`` (não saem do computador do bot); ``computador_agir`` passa pelo revisor, porque um
clique no navegador do computador pode enviar algo para fora. Nenhuma entra em rotina sem
supervisão (nem aparece, nem roda).

O serviço nasce no primeiro uso dentro do worker (``obter_servico``); o desligamento por
ociosidade é o cron ``workers.computador.desligar_computadores_ociosos``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.computador.interface import MAX_ACOES_POR_CHAMADA, AcaoComputador, Alvo
from app.computador.servico import ServicoComputador
from app.ferramentas.base import ContextoFerramenta

AlvoTexto = Literal["virtual", "pc_usuario"]

NOMES = (
    "computador_observar",
    "computador_agir",
    "computador_arquivos",
    "computador_escrever_arquivo",
    "computador_desligar",
)


class ComputadorObservar(BaseModel):
    """Olha a tela do seu computador virtual (Linux com navegador e terminal): tamanho, janelas
    abertas com refs @cN:jM e a janela ativa. Liga o computador na primeira vez. Use antes de
    agir e sempre que a tela puder ter mudado."""

    alvo: AlvoTexto = "virtual"


class ComputadorAgir(BaseModel):
    """Faz até 5 ações seguidas no seu computador virtual (clicar, clique_duplo, clicar_direito,
    digitar, tecla, rolar, arrastar, abrir navegador/terminal) e confere a tela depois. Use x/y
    da última captura ou a ref de uma janela. Nunca digite senhas nem chaves."""

    acoes: list[AcaoComputador] = Field(min_length=1, max_length=MAX_ACOES_POR_CHAMADA)
    alvo: AlvoTexto = "virtual"


class ComputadorArquivos(BaseModel):
    """Lista ou lê arquivos da sua área no computador virtual (downloads do navegador caem
    nela). Caminhos são relativos à área."""

    operacao: Literal["listar", "ler"] = "listar"
    caminho: str = Field(default="", max_length=300)
    alvo: AlvoTexto = "virtual"


class ComputadorEscreverArquivo(BaseModel):
    """Grava um arquivo de texto na sua área do computador virtual (máximo 1 MB)."""

    caminho: str = Field(min_length=1, max_length=300)
    conteudo: str = Field(max_length=1_000_000)
    alvo: AlvoTexto = "virtual"


class ComputadorDesligar(BaseModel):
    """Desliga o seu computador virtual quando terminar (a área de arquivos é apagada)."""


ESQUEMAS: dict[str, type[BaseModel]] = {
    "computador_observar": ComputadorObservar,
    "computador_agir": ComputadorAgir,
    "computador_arquivos": ComputadorArquivos,
    "computador_escrever_arquivo": ComputadorEscreverArquivo,
    "computador_desligar": ComputadorDesligar,
}

_servico: ServicoComputador | None = None


def configurar(servico: ServicoComputador | None) -> None:
    """Troca o serviço (testes) ou zera para nascer de novo no próximo uso."""
    global _servico
    _servico = servico


def obter_servico() -> ServicoComputador:
    global _servico
    if _servico is None:
        from app.computador.pc_usuario import ProvedorPcUsuario
        from app.computador.virtual import ClienteDocker, GerenteComputadoresDocker
        from app.core.config import obter_configuracao
        from app.eventos.equipe import publicar_evento_equipe
        from app.ferramentas.ambiente import redis_dos_eventos

        config = obter_configuracao()
        redis = redis_dos_eventos()

        async def publicar(evento, usuario_id) -> None:
            await publicar_evento_equipe(redis, evento, usuario_id)

        _servico = ServicoComputador(
            provedores={
                Alvo.VIRTUAL: GerenteComputadoresDocker(
                    ClienteDocker(docker_host=config.sandbox_docker_host or None),
                    imagem=config.computador_imagem,
                    imagem_proxy=config.computador_proxy_imagem,
                ),
                Alvo.PC_USUARIO: ProvedorPcUsuario(),
            },
            redis=redis,
            publicar=publicar,
            virtual_ativo=lambda: obter_configuracao().sandbox_ativo,
        )
    return _servico


async def computador_observar(args: ComputadorObservar, contexto: ContextoFerramenta) -> str:
    return await obter_servico().observar(contexto, Alvo(args.alvo))


async def computador_agir(args: ComputadorAgir, contexto: ContextoFerramenta) -> str:
    return await obter_servico().agir(contexto, args.acoes, Alvo(args.alvo))


async def computador_arquivos(args: ComputadorArquivos, contexto: ContextoFerramenta) -> str:
    return await obter_servico().arquivos(contexto, args.operacao, args.caminho, Alvo(args.alvo))


async def computador_escrever_arquivo(
    args: ComputadorEscreverArquivo, contexto: ContextoFerramenta
) -> str:
    return await obter_servico().escrever(contexto, args.caminho, args.conteudo, Alvo(args.alvo))


async def computador_desligar(args: ComputadorDesligar, contexto: ContextoFerramenta) -> str:
    return await obter_servico().desligar(contexto)


def registrar(esquemas: dict[str, type[BaseModel]], modulos: dict[str, str]) -> None:
    """Liga as ferramentas no registro (``app/ferramentas/registro.py``)."""
    esquemas.update(ESQUEMAS)
    modulos.update(dict.fromkeys(ESQUEMAS, __name__))

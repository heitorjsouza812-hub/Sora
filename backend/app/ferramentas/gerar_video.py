"""Ferramenta ``gerar_video`` (Onda 3, item 17): vídeo curto pela conta do Google do usuário.

Sempre pede aprovação (cartão fixo, nem o modo automático libera): o cartão mostra a duração, a
qualidade e o custo estimado em dólar. Rotina sem ninguém olhando não gera vídeo. O MP4 vira
anexo (``origem = especialista``) e vai junto da próxima mensagem do bot, como as imagens.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ferramentas.arquivos import pasta_da_cadeia
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao, raiz_dos_arquivos
from app.ferramentas.saidas_do_turno import registrar
from app.llm.custo import CustoChamada, gravar_chamada
from app.llm.provedores import ErroProvedor
from app.llm.video import DURACAO_MAXIMA, DURACAO_MINIMA, custo_estimado
from app.llm.video import gerar_video as gerar
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.tabelas import Anexo, Provedor


class GerarVideo(BaseModel):
    """Gera um vídeo curto (3 a 15 s) a partir de uma descrição. Custa dinheiro na conta do
    Google do usuário e sempre pede a aprovação dele antes."""

    descricao: str = Field(min_length=1, max_length=4_000, description="O que o vídeo mostra.")
    proporcao: Literal["16:9", "9:16"] = "16:9"
    duracao: int = Field(default=8, ge=DURACAO_MINIMA, le=DURACAO_MAXIMA, description="Segundos.")
    qualidade: Literal["360p", "720p", "1080p"] = "720p"


def texto_do_custo(argumentos: dict[str, Any]) -> str:
    """Linha "O que pode acontecer" do cartão: o custo estimado na conta do Google."""
    try:
        duracao = int(argumentos.get("duracao") or 8)
    except (TypeError, ValueError):
        duracao = 8
    qualidade = str(argumentos.get("qualidade") or "720p")
    valor = custo_estimado(duracao, qualidade)
    return (
        f"Cobra na sua conta do Google: cerca de US$ {str(valor).replace('.', ',')} "
        f"({duracao} s em {qualidade})."
    )


def _gravar(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)


async def gerar_video(args: GerarVideo, contexto: ContextoFerramenta) -> str:
    from app.seletor.repositorio import config_do_provedor

    async with abrir_sessao() as sessao:
        provedor_id = await sessao.scalar(
            select(Provedor.id)
            .where(
                Provedor.usuario_id == contexto.usuario_id,
                Provedor.tipo == TipoProvedor.GOOGLE,
                Provedor.apagado_em.is_(None),
            )
            .order_by(Provedor.criado_em)
            .limit(1)
        )
        if provedor_id is None:
            from app.llm.falso import modelo_falso_ativo

            if not modelo_falso_ativo():
                raise ErroFerramenta(
                    "Para gerar vídeo, o usuário precisa conectar uma conta do Google (Gemini) em "
                    "Configurações → Modelos de IA."
                )
            from app.llm.provedores import ConfigProvedor

            config = ConfigProvedor(tipo=TipoProvedor.GOOGLE)
        else:
            config = await config_do_provedor(sessao, contexto.usuario_id, provedor_id)
    try:
        video = await gerar(
            config,
            args.descricao,
            proporcao=args.proporcao,
            duracao=args.duracao,
            qualidade=args.qualidade,
        )
    except (ErroProvedor, ValueError) as erro:
        raise ErroFerramenta(str(erro)) from erro

    raiz = raiz_dos_arquivos().resolve()
    pasta = pasta_da_cadeia(raiz, contexto.usuario_id, contexto.cadeia_id or contexto.conversa_id)
    anexo_id = uuid.uuid4()
    nome = f"video-{anexo_id.hex[:8]}.mp4"
    destino = pasta / nome
    await asyncio.to_thread(_gravar, destino, video.conteudo)
    async with abrir_sessao() as sessao:
        sessao.add(
            Anexo(
                id=anexo_id,
                usuario_id=contexto.usuario_id,
                nome=nome,
                tipo=video.tipo_mime,
                tamanho=len(video.conteudo),
                caminho=destino.relative_to(raiz).as_posix(),
                origem="especialista",
            )
        )
        await gravar_chamada(
            sessao,
            contexto.usuario_id,
            CustoChamada(
                provedor_id=config.provedor_id,
                papel="video",
                modelo=video.modelo,
                nivel="especial",
                tokens_entrada=0,
                tokens_saida=0,
                custo_usd=video.custo_usd,
                latencia_ms=0,
            ),
            cadeia_id=contexto.cadeia_id,
            etapa_id=contexto.etapa_id,
        )
    await registrar(contexto.usuario_id, contexto.agente_id, anexo_id)
    return (
        f"Vídeo de {args.duracao} s gerado. anexo_id: {anexo_id}. "
        "Ele vai junto com a sua próxima mensagem ao usuário."
    )

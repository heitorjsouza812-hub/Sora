"""Anexos do usuário que chegam ao modelo (item 10 da etapa 6).

Antes, a mensagem do usuário entrava no agente só como texto: o modelo nem sabia que havia
anexo. Agora o texto leva a lista dos arquivos (com o ``anexo_id`` para ``ler_anexo``) e as
**imagens** vão como ``image_url`` quando o modelo escolhido enxerga (capacidade ``visao`` do
seletor, inclusive a que o usuário marcou). Sem visão, o bot recebe uma nota e o usuário recebe
um aviso em PT-BR no chat.

Só lê anexos do próprio usuário (``Anexo.usuario_id``); o caminho salvo passa por
``caminho_do_anexo``. A parte pura (``montar_entrada``) não toca banco nem disco: ``ler`` entra
por parâmetro, para os testes.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from sqlalchemy.ext.asyncio import AsyncSession

registro = logging.getLogger(__name__)

MAX_IMAGENS = 4
MAX_BYTES_IMAGEM = 5 * 1024 * 1024
TIPOS_IMAGEM = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})

AVISO_SEM_VISAO = (
    "O modelo que está respondendo não enxerga imagens, então não consegui ver {quais}. "
    "Para eu olhar imagens, escolha um modelo com visão em Configurações → Modelos de IA "
    "(ou marque a capacidade de visão num modelo que já a tenha)."
)
NOTA_SEM_VISAO = (
    "O usuário anexou imagem(ns) que você NÃO consegue ver porque o modelo atual não tem visão. "
    "O usuário já foi avisado disso: não repita o aviso e não invente o que a imagem mostra. "
    "Responda ao resto do pedido; se a imagem for essencial, diga em uma frase que precisa de "
    "um modelo com visão."
)


NOTA_SEM_VISAO_NO_GRUPO = (
    "O usuário anexou imagem(ns) que você NÃO consegue ver porque o modelo atual não tem visão. "
    "Não invente o que a imagem mostra. Responda ao resto do pedido e avise o usuário, em uma "
    "frase no seu resultado, que precisa de um modelo com visão (Configurações → Modelos de IA)."
)


@dataclass(frozen=True, slots=True)
class AnexoDaEntrada:
    id: UUID
    nome: str
    tipo: str
    tamanho: int
    caminho: str


@dataclass(slots=True)
class EntradaDoUsuario:
    """O que vira a ``HumanMessage`` do turno e o que o usuário precisa saber."""

    conteudo: str | list[dict[str, Any]]
    imagens_enviadas: int = 0
    avisos: list[str] = field(default_factory=list)

    def com_texto(self, antigo: str, novo: str) -> EntradaDoUsuario:
        """Troca o pedido original por ``novo`` (a habilidade forçada reescreve só o pedido)."""
        if isinstance(self.conteudo, str):
            conteudo: str | list[dict[str, Any]] = self.conteudo.replace(antigo, novo, 1)
        else:
            conteudo = [dict(bloco) for bloco in self.conteudo]
            primeiro = conteudo[0]
            if primeiro.get("type") == "text":
                primeiro["text"] = str(primeiro["text"]).replace(antigo, novo, 1)
        return EntradaDoUsuario(conteudo, self.imagens_enviadas, list(self.avisos))


def _escapar(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lista(anexos: Iterable[AnexoDaEntrada]) -> str:
    linhas = [f"- {_escapar(a.nome)} ({a.tipo}) — anexo_id: {a.id}" for a in anexos]
    return "<anexos_do_usuario>\n" + "\n".join(linhas) + "\n</anexos_do_usuario>"


def _quais(nomes: list[str]) -> str:
    if len(nomes) == 1:
        return f"a imagem {nomes[0]}"
    return "as imagens " + ", ".join(nomes)


async def montar_entrada(
    texto: str,
    anexos: list[AnexoDaEntrada],
    *,
    tem_visao: bool,
    ler: Callable[[AnexoDaEntrada], Awaitable[bytes]],
    usuario_avisado: bool = True,
) -> EntradaDoUsuario:
    """Texto + lista de anexos + imagens (se o modelo enxerga). Sem anexos, o texto passa igual."""
    if not anexos:
        return EntradaDoUsuario(conteudo=texto)
    imagens = [a for a in anexos if a.tipo in TIPOS_IMAGEM]
    cabecalho = f"{texto}\n\n{_lista(anexos)}" if texto.strip() else _lista(anexos)
    if not imagens:
        return EntradaDoUsuario(conteudo=cabecalho)

    if not tem_visao:
        nomes = [a.nome for a in imagens]
        if not usuario_avisado:  # grupo: não há mensagem avulsa do bot; ele avisa no resultado
            return EntradaDoUsuario(conteudo=f"{cabecalho}\n\n{NOTA_SEM_VISAO_NO_GRUPO}")
        return EntradaDoUsuario(
            conteudo=f"{cabecalho}\n\n{NOTA_SEM_VISAO}",
            avisos=[AVISO_SEM_VISAO.format(quais=_quais(nomes))],
        )

    blocos: list[dict[str, Any]] = []
    sem_ver: list[str] = []
    limite_mb = MAX_BYTES_IMAGEM // (1024 * 1024)
    for imagem in imagens:
        if len(blocos) >= MAX_IMAGENS:
            sem_ver.append(f"{imagem.nome} (passa de {MAX_IMAGENS} imagens por mensagem)")
            continue
        if imagem.tamanho > MAX_BYTES_IMAGEM:
            sem_ver.append(f"{imagem.nome} (passa de {limite_mb} MB)")
            continue
        try:
            dados = await ler(imagem)
        except Exception:
            registro.warning("não consegui ler a imagem %s", imagem.id, exc_info=True)
            sem_ver.append(f"{imagem.nome} (não consegui abrir o arquivo)")
            continue
        if len(dados) > MAX_BYTES_IMAGEM:
            sem_ver.append(f"{imagem.nome} (passa de {limite_mb} MB)")
            continue
        codigo = base64.b64encode(dados).decode("ascii")
        blocos.append(
            {"type": "image_url", "image_url": {"url": f"data:{imagem.tipo};base64,{codigo}"}}
        )

    avisos: list[str] = []
    texto_final = cabecalho
    if sem_ver:
        resto = " As outras seguiram." if blocos else ""
        avisos.append("Não consegui mostrar ao modelo: " + "; ".join(sem_ver) + "." + resto)
        texto_final += (
            "\n\nNão foi possível enviar estas imagens a você (o usuário já foi avisado): "
            + "; ".join(sem_ver)
            + "."
        )
    if not blocos:
        return EntradaDoUsuario(conteudo=texto_final, avisos=avisos)
    return EntradaDoUsuario(
        conteudo=[{"type": "text", "text": texto_final}, *blocos],
        imagens_enviadas=len(blocos),
        avisos=avisos,
    )


async def anexos_do_dono(
    sessao: AsyncSession, usuario_id: UUID, ids: Iterable[UUID | str]
) -> list[AnexoDaEntrada]:
    """Anexos pedidos que pertencem ao usuário, na ordem pedida; o resto some em silêncio."""
    from sqlalchemy import select

    from app.modelos.tabelas import Anexo

    pedidos = list(dict.fromkeys(UUID(str(i)) for i in ids))
    if not pedidos:
        return []
    linhas = (
        await sessao.scalars(
            select(Anexo).where(Anexo.usuario_id == usuario_id, Anexo.id.in_(pedidos))
        )
    ).all()
    por_id = {linha.id: linha for linha in linhas}
    return [
        AnexoDaEntrada(achado.id, achado.nome, achado.tipo, achado.tamanho, achado.caminho)
        for i in pedidos
        if (achado := por_id.get(i)) is not None
    ]


async def ler_do_disco(anexo: AnexoDaEntrada) -> bytes:
    from app.ferramentas.arquivos import caminho_do_anexo
    from app.ferramentas.infra import raiz_dos_arquivos

    caminho = caminho_do_anexo(raiz_dos_arquivos(), anexo.caminho)
    return await asyncio.to_thread(caminho.read_bytes)


async def modelos_com_visao(
    sessao: AsyncSession,
    usuario_id: UUID,
    papel: str,
    *,
    dificuldade: int = 1,
    conversa_privada: bool = False,
) -> tuple[list[BaseChatModel], bool]:
    """Modelos do papel que enxergam, ou, se o usuário não tem nenhum, os de sempre e ``False``.

    O seletor já filtra pela capacidade ``visao``, então todo o fallback também enxerga."""
    from app.llm.falso import modelo_falso_ativo
    from app.orquestrador.modelos import SemModeloDisponivel, modelos_do_papel
    from app.seletor.tipos import Capacidade

    if modelo_falso_ativo():
        modelos = await modelos_do_papel(
            sessao, usuario_id, papel, dificuldade=dificuldade, conversa_privada=conversa_privada
        )
        return modelos, True
    try:
        modelos = await modelos_do_papel(
            sessao,
            usuario_id,
            papel,
            dificuldade=dificuldade,
            precisa=(Capacidade.FERRAMENTAS, Capacidade.VISAO),
            conversa_privada=conversa_privada,
        )
        return modelos, True
    except SemModeloDisponivel:
        modelos = await modelos_do_papel(
            sessao, usuario_id, papel, dificuldade=dificuldade, conversa_privada=conversa_privada
        )
        return modelos, False


async def preparar_entrada(
    sessao: AsyncSession,
    usuario_id: UUID,
    texto: str,
    anexo_ids: Iterable[UUID | str],
    papel: str,
    *,
    dificuldade: int = 1,
    conversa_privada: bool = False,
    usuario_avisado: bool = True,
) -> tuple[EntradaDoUsuario, list[BaseChatModel]]:
    """Carrega os anexos do dono, escolhe os modelos (com visão se houver imagem) e monta a
    entrada do turno. Sem anexos, só escolhe os modelos de sempre."""
    from app.orquestrador.modelos import modelos_do_papel

    anexos = await anexos_do_dono(sessao, usuario_id, anexo_ids)
    if any(a.tipo in TIPOS_IMAGEM for a in anexos):
        modelos, tem_visao = await modelos_com_visao(
            sessao, usuario_id, papel, dificuldade=dificuldade, conversa_privada=conversa_privada
        )
    else:
        modelos = await modelos_do_papel(
            sessao, usuario_id, papel, dificuldade=dificuldade, conversa_privada=conversa_privada
        )
        tem_visao = True
    entrada = await montar_entrada(
        texto, anexos, tem_visao=tem_visao, ler=ler_do_disco, usuario_avisado=usuario_avisado
    )
    return entrada, modelos

"""Chaves extras por conexão e modelos reserva da conta (migração 0019).

**Chaves extras.** Uma conexão (provedor + URL) pode ter até ``MAX_CHAVES_EXTRAS`` chaves além da
principal, por exemplo duas contas grátis da Groq. No worker, cada modelo da lista ganha, logo
depois dele, o mesmo modelo com cada chave extra: quando a chave principal bate no limite, a
conversa continua no **mesmo modelo** com a próxima chave, e a troca aparece na linha do tempo.
Cada chave é testada (listagem de modelos, sem geração paga) antes de entrar e fica cifrada como a
principal, com o id da linha no AAD.

**Modelos reserva.** Até ``MAX_RESERVAS`` modelos, em ordem, que só entram quando há um modelo
fixo escolhido no campo de mensagem e ele falha. Sem modelo fixo vale o seletor automático, que já
tem as próprias reservas. A troca nunca é silenciosa: aparece na conversa (decisão de 2026-11-16).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, SecretStr
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.conexoes import (
    ErroConexao,
    ErroDadosProvedor,
    ListadorModelos,
    _chave_final,
    _provedor_do_usuario,
    _testar,
    _validar_chave,
)
from app.llm.provedores import ConfigProvedor
from app.modelos.tabelas import ChaveProvedor, ModeloReserva, Provedor

MAX_CHAVES_EXTRAS = 4
MAX_RESERVAS = 3


class ErroChaveRepetida(ErroConexao):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Essa chave já está nesta conexão.")


class ErroChaveNaoEncontrada(ErroConexao):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Chave não encontrada.")


class ItemReserva(BaseModel):
    provedor_id: UUID
    modelo: str = Field(min_length=1, max_length=200)


def _aad(usuario_id: UUID, provedor_id: UUID, chave_id: UUID) -> dict[str, object]:
    return {"usuario_id": usuario_id, "provedor": f"{provedor_id}:chave:{chave_id}"}


async def _decifrar_extra(sessao: AsyncSession, usuario_id: UUID, linha: ChaveProvedor) -> str:
    aad = _aad(usuario_id, linha.provedor_id, linha.id)
    if seguranca.precisa_recifrar(linha.chave_cifrada):  # rotação da chave mestra (§8.1)
        linha.chave_cifrada = seguranca.recifrar_segredo(linha.chave_cifrada, **aad)
        await sessao.flush()
    return seguranca.decifrar_segredo(linha.chave_cifrada, **aad)


async def _extras_do(sessao: AsyncSession, provedor_id: UUID) -> list[ChaveProvedor]:
    return list(
        (
            await sessao.scalars(
                select(ChaveProvedor)
                .where(ChaveProvedor.provedor_id == provedor_id)
                .order_by(ChaveProvedor.criado_em, ChaveProvedor.id)
            )
        ).all()
    )


async def listar_chaves(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID
) -> list[ChaveProvedor]:
    """Chaves extras da conexão do usuário (só o final de cada uma sai daqui para o app)."""
    await _provedor_do_usuario(sessao, usuario_id, provedor_id)
    return await _extras_do(sessao, provedor_id)


async def adicionar_chave(
    sessao: AsyncSession,
    redis: Redis,
    usuario_id: UUID,
    provedor_id: UUID,
    chave: SecretStr | None,
    listador: ListadorModelos,
) -> ChaveProvedor:
    """Testa a chave no mesmo provedor e URL da conexão e guarda cifrada."""
    provedor = await _provedor_do_usuario(sessao, usuario_id, provedor_id)
    await sessao.refresh(provedor, with_for_update=True)  # serializa adições da mesma conexão
    limpa = _validar_chave(provedor.tipo, chave)
    if limpa is None:
        raise ErroDadosProvedor("Informe a chave da API.")
    extras = await _extras_do(sessao, provedor.id)
    if len(extras) >= MAX_CHAVES_EXTRAS:
        raise ErroDadosProvedor(f"Cada conexão aceita até {MAX_CHAVES_EXTRAS} chaves extras.")
    if provedor.chave_cifrada:
        principal = seguranca.decifrar_segredo(
            provedor.chave_cifrada, usuario_id=usuario_id, provedor=str(provedor.id)
        )
        if principal == limpa:
            raise ErroChaveRepetida()
    for extra in extras:
        if await _decifrar_extra(sessao, usuario_id, extra) == limpa:
            raise ErroChaveRepetida()
    config = ConfigProvedor(
        provedor_id=provedor.id, tipo=provedor.tipo, api_key=limpa, base_url=provedor.base_url
    )
    await _testar(redis, usuario_id, config, listador)
    chave_id = uuid4()
    linha = ChaveProvedor(
        id=chave_id,
        provedor_id=provedor.id,
        chave_cifrada=seguranca.cifrar_segredo(limpa, **_aad(usuario_id, provedor.id, chave_id)),
        chave_final=_chave_final(limpa),
    )
    sessao.add(linha)
    await sessao.flush()
    await sessao.refresh(linha)
    return linha


async def remover_chave(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID, chave_id: UUID
) -> None:
    await _provedor_do_usuario(sessao, usuario_id, provedor_id)
    resultado = await sessao.execute(
        delete(ChaveProvedor).where(
            ChaveProvedor.id == chave_id, ChaveProvedor.provedor_id == provedor_id
        )
    )
    if not resultado.rowcount:
        raise ErroChaveNaoEncontrada()


async def apagar_extras_e_reservas_do_provedor(sessao: AsyncSession, provedor_id: UUID) -> None:
    """A conexão foi apagada (logicamente): as chaves extras somem de verdade, e as reservas que
    apontavam para ela também."""
    await sessao.execute(delete(ChaveProvedor).where(ChaveProvedor.provedor_id == provedor_id))
    await sessao.execute(delete(ModeloReserva).where(ModeloReserva.provedor_id == provedor_id))


async def configs_extras(
    sessao: AsyncSession, usuario_id: UUID, provedor_id: UUID
) -> list[ConfigProvedor]:
    """Worker: as chaves extras decifradas, na ordem em que foram adicionadas."""
    provedor = await sessao.get(Provedor, provedor_id)
    if provedor is None or provedor.usuario_id != usuario_id or provedor.apagado_em is not None:
        return []
    return [
        ConfigProvedor(
            provedor_id=provedor.id,
            tipo=provedor.tipo,
            api_key=SecretStr(await _decifrar_extra(sessao, usuario_id, linha)),
            base_url=provedor.base_url,
        )
        for linha in await _extras_do(sessao, provedor.id)
    ]


# ---------- modelos reserva ----------


async def listar_reservas(sessao: AsyncSession, usuario_id: UUID) -> list[ModeloReserva]:
    """Reservas da conta, em ordem, só das conexões que ainda existem."""
    return list(
        (
            await sessao.scalars(
                select(ModeloReserva)
                .join(Provedor, Provedor.id == ModeloReserva.provedor_id)
                .where(ModeloReserva.usuario_id == usuario_id, Provedor.apagado_em.is_(None))
                .order_by(ModeloReserva.ordem, ModeloReserva.criado_em)
            )
        ).all()
    )


async def definir_reservas(
    sessao: AsyncSession, usuario_id: UUID, itens: Sequence[ItemReserva]
) -> list[ModeloReserva]:
    """Troca a lista inteira. Cada item precisa ser um modelo de conversa ativo do usuário."""
    from app.preferencias_conversa import ErroPreferencia, _conferir_modelo

    if len(itens) > MAX_RESERVAS:
        raise ErroDadosProvedor(f"Escolha até {MAX_RESERVAS} modelos reserva.")
    pares = [(item.provedor_id, item.modelo.strip()) for item in itens]
    if len(set(pares)) != len(pares):
        raise ErroDadosProvedor("O mesmo modelo apareceu duas vezes na lista de reserva.")
    for provedor_id, modelo in pares:
        try:
            await _conferir_modelo(sessao, usuario_id, provedor_id, modelo)
        except ErroPreferencia as erro:
            raise ErroDadosProvedor(str(erro)) from erro
    await sessao.execute(delete(ModeloReserva).where(ModeloReserva.usuario_id == usuario_id))
    linhas = [
        ModeloReserva(usuario_id=usuario_id, provedor_id=provedor_id, modelo=modelo, ordem=ordem)
        for ordem, (provedor_id, modelo) in enumerate(pares)
    ]
    sessao.add_all(linhas)
    await sessao.flush()
    return linhas

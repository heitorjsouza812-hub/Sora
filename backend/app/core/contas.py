"""Regras de contas e sessões; especificação §8.2.

Funções puras (`classificar_token`, `cliente_da_requisicao`) ficam separadas das que falam com o
banco para poderem ser testadas sem PostgreSQL.
"""

import asyncio
import json
import logging
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import (
    ColumnElement,
    ForeignKey,
    Select,
    Table,
    delete,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.redis import (
    devolver_vaga,
    limpar_limite,
    reservar_vaga,
    verificar_limite,
)
from app.eventos.streams import canal_conversa, canal_usuario
from app.ferramentas.arquivos import CaminhoInseguro, caminho_do_anexo, dentro_da_pasta
from app.modelos.base import Base
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import CadastroEntrada, LoginEntrada
from app.modelos.tabelas import (
    Agente,
    Anexo,
    Cadeia,
    Conversa,
    Convite,
    Etapa,
    Provedor,
    Sessao,
    Usuario,
)

registro = logging.getLogger(__name__)

CABECALHO_CLIENTE = "X-Sora-Cliente"
CLIENTE_WEB = "web"
CLIENTE_DESKTOP = "desktop"
JANELA_TOLERANCIA_RENOVACAO = timedelta(seconds=30)
"""Tempo para recuperar uma resposta de renovação perdida devolvendo o MESMO par (idempotente:
várias abas renovando juntas recebem o mesmo token)."""
JANELA_REEMISSAO = timedelta(minutes=5)
"""Depois dos 30 s e até aqui, o token imediatamente anterior ainda pode pedir um par NOVO, se o
atual nunca foi usado (resposta perdida em F5 seguidos). Passado isso, é reuso: a família cai."""
MAX_REEMISSOES = 3
"""Quantas reemissões seguidas a partir do mesmo token anterior. Cada uma joga o token atual (nunca
usado) no histórico: se ele aparecer depois, havia duas cópias da sessão e a família é revogada."""
MAX_HISTORICO_HASHES = 20
"""Gerações antigas de token lembradas por sessão (para detectar reuso). Mais velhas que isso são
esquecidas: o token antigo continua recusado (``invalido``), só deixa de revogar a família."""
RETENCAO_SESSOES_VENCIDAS = timedelta(days=30)
"""Sessões encerradas ou vencidas há mais que isto são apagadas pela rotina do worker."""

# Login: só **falhas** contam (API-04). O limite curto é por e-mail + IP, então quem não está no
# IP da vítima não a tranca; o teto por e-mail (todas as origens) só segura força bruta
# distribuída e é alto o bastante para não virar bloqueio barato.
LIMITE_LOGIN_EMAIL_IP = (5, 15 * 60)
LIMITE_LOGIN_IP = (20, 15 * 60)
LIMITE_LOGIN_EMAIL = (50, 60 * 60)
LIMITE_CADASTRO_IP = (5, 60 * 60)
# DELETE /v1/conta: senhas erradas por usuário (um token roubado não serve de oráculo de senha).
LIMITE_APAGAR_CONTA = (5, 15 * 60)

TABELAS_CHECKPOINT = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")
"""Tabelas do ``AsyncPostgresSaver`` (criadas pelo ``setup()`` do worker), por ``thread_id``."""

# Hash fixo para gastar o mesmo tempo quando o e-mail não existe (não revela quem tem conta).
_HASH_FALSO = seguranca.gerar_hash_senha("senha-falsa-para-tempo-constante")


class ErroConta(Exception):
    """Erro de negócio das contas, traduzido em resposta HTTP pelo handler da aplicação."""

    status_code = 400

    def __init__(self, detalhe: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(detalhe)
        self.detalhe = detalhe
        self.headers = headers or {}


class ErroLimite(ErroConta):
    status_code = 429

    def __init__(self, segundos: int) -> None:
        super().__init__(
            "Muitas tentativas. Tente de novo em alguns instantes.",
            {"Retry-After": str(segundos)},
        )


class ErroCredenciais(ErroConta):
    status_code = 401

    def __init__(self, detalhe: str = "E-mail ou senha incorretos.") -> None:
        super().__init__(detalhe)


class ErroConvite(ErroConta):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("Convite inválido ou já usado.")


class ErroEmailEmUso(ErroConta):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Já existe uma conta com este e-mail.")


class ErroSenhaIncorreta(ErroConta):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("Senha incorreta.")


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def cliente_da_requisicao(cabecalho: str | None) -> str:
    """`desktop` só com `X-Sora-Cliente: desktop`; qualquer outro valor é navegador."""
    return CLIENTE_DESKTOP if (cabecalho or "").strip().lower() == CLIENTE_DESKTOP else CLIENTE_WEB


def classificar_token(
    sessao: Sessao | None, token_hash: str, agora: datetime
) -> Literal["valido", "tolerado", "reemitir", "reutilizado", "invalido"]:
    """Classifica o token de renovação apresentado.

    - ``tolerado``: o anterior, até 30 s depois da rotação (devolve o mesmo par guardado).
    - ``reemitir``: o anterior, de 30 s a 5 min depois, com o atual nunca usado (se fosse usado, o
      anterior já estaria no histórico) e no máximo ``MAX_REEMISSOES`` vezes: é a resposta da
      renovação que se perdeu (F5 seguidos), não roubo. O atual vai para o histórico.
    - ``reutilizado``: qualquer outro uso de token velho; a família inteira é revogada.
    """
    if sessao is None or sessao.encerrada_em is not None or sessao.expira_em <= agora:
        return "invalido"
    if sessao.token_hash == token_hash:
        return "valido"
    if sessao.anterior_hash == token_hash:
        if sessao.anterior_rotacionado_em is None:
            return "reutilizado"
        desde_rotacao = agora - sessao.anterior_rotacionado_em
        if timedelta(0) <= desde_rotacao <= JANELA_TOLERANCIA_RENOVACAO:
            return "tolerado"
        if desde_rotacao <= JANELA_REEMISSAO and (sessao.reemissoes or 0) < MAX_REEMISSOES:
            return "reemitir"
        return "reutilizado"
    return "reutilizado" if token_hash in (sessao.historico_hashes or []) else "invalido"


async def _limitar(redis: Redis, chave: str, limite: tuple[int, int]) -> None:
    espera = await verificar_limite(redis, chave, *limite)
    if espera:
        raise ErroLimite(espera)


def _chaves_de_login(email: str, ip: str | None) -> dict[str, tuple[int, int]]:
    origem = ip or "desconhecido"
    return {
        f"login:falha:email_ip:{email}:{origem}": LIMITE_LOGIN_EMAIL_IP,
        f"login:falha:ip:{origem}": LIMITE_LOGIN_IP,
        f"login:falha:email:{email}": LIMITE_LOGIN_EMAIL,
    }


async def cadastrar(
    sessao: AsyncSession, redis: Redis, dados: CadastroEntrada, ip: str | None
) -> None:
    """Cria a conta (e a Sora dela) consumindo um convite; na fase 1 o convite é obrigatório.

    O convite é conferido **antes** do e-mail (VAL-08): sem convite válido a resposta é sempre
    403, então ninguém sonda quais e-mails têm conta. Com e-mail em uso, a exceção desfaz a
    transação e o convite volta.
    """
    await _limitar(redis, f"cadastro:ip:{ip}", LIMITE_CADASTRO_IP)
    email = normalizar_email(dados.email)
    if not dados.convite:
        raise ErroConvite()
    consumido = await sessao.execute(
        update(Convite)
        .where(Convite.codigo == dados.convite, Convite.usos_restantes > 0)
        .values(usos_restantes=Convite.usos_restantes - 1)
        .returning(Convite.codigo)
    )
    if consumido.first() is None:
        raise ErroConvite()
    if await sessao.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        raise ErroEmailEmUso()
    usuario = Usuario(
        email=email,
        nome=dados.nome.strip(),
        senha_hash=await seguranca.gerar_hash_senha_em_thread(dados.senha),
    )
    sessao.add(usuario)
    try:
        await sessao.flush()
    except IntegrityError as erro:  # dois cadastros simultâneos com o mesmo e-mail
        raise ErroEmailEmUso() from erro
    sessao.add(
        Agente(
            usuario_id=usuario.id,
            tipo=TipoAgente.SORA,
            nome="Sora",
            cor="#E2ECFF",
            perfil_navegador="compartilhado",  # a Sora usa o login da conta; bots, o próprio
        )
    )
    await sessao.flush()


async def _abrir_sessao(
    sessao: AsyncSession, usuario_id: UUID, cliente: str, ip: str | None, agente_usuario: str | None
) -> tuple[str, str]:
    token, token_hash = seguranca.gerar_token_renovacao()
    nova = Sessao(
        usuario_id=usuario_id,
        token_hash=token_hash,
        cliente=cliente,
        expira_em=datetime.now(UTC) + seguranca.RENOVACAO_VALIDADE,
        ip=ip,
        agente_usuario=agente_usuario,
    )
    sessao.add(nova)
    await sessao.flush()
    return token, _token_acesso_da_sessao(nova)


async def entrar(
    sessao: AsyncSession,
    redis: Redis,
    dados: LoginEntrada,
    cliente: str,
    ip: str | None,
    agente_usuario: str | None,
) -> tuple[str, str]:
    """Autentica; devolve (token de renovação, token de acesso).

    Os limites contam só senhas erradas; o login certo apaga as falhas do par e-mail + IP.
    """
    email = normalizar_email(dados.email)
    chaves = _chaves_de_login(email, ip)
    # Reserva atômica de uma "falha" em cada contador: tentativas simultâneas não furam o
    # limite. Login certo devolve as reservas; senha errada as mantém.
    reservas: dict[str, str | None] = {}
    for chave, (limite, janela) in chaves.items():
        espera, membro = await reservar_vaga(redis, chave, limite, janela)
        if espera:
            for chave_feita, membro_feito in reservas.items():
                await devolver_vaga(redis, chave_feita, membro_feito)
            raise ErroLimite(espera)
        reservas[chave] = membro
    usuario = await sessao.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    senha_ok = await seguranca.verificar_senha_em_thread(
        dados.senha, usuario.senha_hash if usuario else _HASH_FALSO
    )
    if usuario is None or not senha_ok:
        raise ErroCredenciais()
    for chave, membro in reservas.items():
        await devolver_vaga(redis, chave, membro)
    await limpar_limite(redis, next(iter(chaves)))
    return await _abrir_sessao(sessao, usuario.id, cliente, ip, agente_usuario)


def consulta_sessao_do_token(token_hash: str, *, travar: bool = False) -> Select[tuple[Sessao]]:
    """``select`` da sessão pelo token atual ou anterior; ``travar`` = ``FOR UPDATE``."""
    consulta = select(Sessao).where(
        (Sessao.token_hash == token_hash)
        | (Sessao.anterior_hash == token_hash)
        | Sessao.historico_hashes.contains([token_hash])
    )
    return consulta.with_for_update() if travar else consulta


async def _sessao_do_token(
    sessao: AsyncSession, token_hash: str, *, travar: bool = False
) -> Sessao | None:
    return await sessao.scalar(consulta_sessao_do_token(token_hash, travar=travar))


def par_vencido(sessao: Sessao, agora: datetime) -> bool:
    """O par guardado só serve à recuperação de resposta perdida, dentro da janela de 30 s."""
    rotacionado = sessao.anterior_rotacionado_em
    return rotacionado is None or agora - rotacionado > JANELA_TOLERANCIA_RENOVACAO


async def limpar_pares_vencidos(sessao: AsyncSession, agora: datetime | None = None) -> int:
    """Zera ``par_atual_cifrado`` das sessões cuja janela de 30 s já fechou (Cerca M4).

    Sem isso o banco guardaria, para sempre, o token de renovação vivo (cifrado com a chave do
    próprio servidor). Roda como rotina do worker; a renovação e a saída também limpam na hora.
    """
    agora = agora or datetime.now(UTC)
    resultado = await sessao.execute(
        update(Sessao)
        .where(
            Sessao.par_atual_cifrado.is_not(None),
            (Sessao.anterior_rotacionado_em.is_(None))
            | (Sessao.anterior_rotacionado_em < agora - JANELA_TOLERANCIA_RENOVACAO),
        )
        .values(par_atual_cifrado=None)
    )
    await sessao.commit()
    return resultado.rowcount or 0


def chave_revogacao_sessao(sessao_id: UUID | str) -> str:
    return f"auth:revogada:sessao:{sessao_id}"


def chave_revogacao_usuario(usuario_id: UUID | str) -> str:
    return f"auth:revogada:usuario:{usuario_id}"


async def revogar_acessos(
    redis: Redis | None, *, sessao_id: UUID | None = None, usuario_id: UUID | None = None
) -> None:
    """Derruba na hora os tokens de ACESSO já emitidos (eles valem 15 min e não ficam no banco).

    Grava uma marca no Redis com a mesma validade do token de acesso; ``usuario_atual`` recusa
    tokens da sessão (ou do usuário) marcados. Falha do Redis não impede sair/apagar."""
    if redis is None:
        return
    validade = int(seguranca.ACESSO_VALIDADE.total_seconds()) + 60
    chaves = []
    if sessao_id is not None:
        chaves.append(chave_revogacao_sessao(sessao_id))
    if usuario_id is not None:
        chaves.append(chave_revogacao_usuario(usuario_id))
    try:
        for chave in chaves:
            await redis.set(chave, "1", ex=validade)
    except Exception:  # revogação é reforço; a sessão já foi encerrada no banco
        registro.warning("não consegui marcar a revogação dos tokens de acesso", exc_info=True)


def _token_acesso_da_sessao(existente: Sessao) -> str:
    dados = {"sub": str(existente.usuario_id), "sid": str(existente.id)}
    return seguranca.criar_token_acesso(dados)


async def renovar(
    sessao: AsyncSession, token: str | None, redis: Redis | None = None
) -> tuple[str, str, str]:
    """Rotaciona uma vez e recupera o mesmo par por 30 s, sob FOR UPDATE.

    A janela não se estende nas recuperações. De 30 s a 5 min, o token anterior ainda ganha um
    par novo se o atual nunca foi usado (``reemitir``: a resposta se perdeu, ex. F5 seguidos).
    Hashes de gerações antigas (as últimas ``MAX_HISTORICO_HASHES``) permitem revogar a família
    mesmo quando o token já não é o imediatamente anterior. O par cifrado some assim que a janela
    fecha.
    """
    if not token:
        raise ErroCredenciais("Sessão expirada. Entre de novo.")
    token_hash = seguranca.hash_token(token)
    existente = await _sessao_do_token(sessao, token_hash, travar=True)
    agora = datetime.now(UTC)
    veredito = classificar_token(existente, token_hash, agora)
    if existente is not None and existente.par_atual_cifrado is not None:
        if veredito != "tolerado" and par_vencido(existente, agora):
            existente.par_atual_cifrado = None  # janela fechada: nada de token vivo guardado
    if veredito == "reutilizado" and existente is not None:
        existente.encerrada_em = agora
        existente.par_atual_cifrado = None
        await sessao.commit()  # o encerramento precisa sobreviver ao erro que sai daqui
        await revogar_acessos(redis, sessao_id=existente.id)
    if veredito not in ("valido", "tolerado", "reemitir") or existente is None:
        raise ErroCredenciais("Sessão expirada. Entre de novo.")
    if veredito == "tolerado":
        if existente.par_atual_cifrado is None:
            raise ErroCredenciais("Sessão expirada. Entre de novo.")
        par = json.loads(
            seguranca.decifrar_segredo(
                existente.par_atual_cifrado,
                usuario_id=existente.usuario_id,
                provedor=f"sessao:{existente.id}",
            )
        )
        return par[0], par[1], existente.cliente
    novo, novo_hash = seguranca.gerar_token_renovacao()
    # O token atual vai para o histórico nos dois casos: na rotação normal ele vira o anterior;
    # na reemissão ele nunca foi usado e é abandonado (se aparecer depois, havia duas cópias).
    existente.historico_hashes = [*(existente.historico_hashes or []), existente.token_hash][
        -MAX_HISTORICO_HASHES:
    ]
    if veredito == "reemitir":
        existente.reemissoes = (existente.reemissoes or 0) + 1  # o anterior continua o mesmo
    else:
        existente.anterior_hash = existente.token_hash
        existente.reemissoes = 0
    existente.anterior_rotacionado_em = agora
    existente.token_hash = novo_hash
    existente.expira_em = agora + seguranca.RENOVACAO_VALIDADE
    await sessao.flush()
    acesso = _token_acesso_da_sessao(existente)
    existente.par_atual_cifrado = seguranca.cifrar_segredo(
        json.dumps([novo, acesso]),
        usuario_id=existente.usuario_id,
        provedor=f"sessao:{existente.id}",
    )
    await sessao.flush()
    return novo, acesso, existente.cliente


async def sair(
    sessao: AsyncSession, token: str | None, redis: Redis | None = None
) -> Sessao | None:
    """Encerra a sessão do token (atual ou anterior) e derruba os tokens de acesso dela.
    Idempotente. Devolve a sessão que acabou de encerrar (``None`` se não havia o que encerrar)."""
    if not token:
        return None
    existente = await _sessao_do_token(sessao, seguranca.hash_token(token))
    if existente is None or existente.encerrada_em is not None:
        return None
    existente.encerrada_em = datetime.now(UTC)
    existente.par_atual_cifrado = None
    await sessao.flush()
    await revogar_acessos(redis, sessao_id=existente.id)
    return existente


async def apagar_sessoes_vencidas(sessao: AsyncSession, agora: datetime | None = None) -> int:
    """Apaga sessões encerradas ou vencidas há mais de ``RETENCAO_SESSOES_VENCIDAS``.

    Sem isso a tabela ``sessoes`` só cresce (cada login e cada aparelho deixam uma linha). Roda
    como rotina do worker, junto da limpeza dos pares cifrados."""
    limite = (agora or datetime.now(UTC)) - RETENCAO_SESSOES_VENCIDAS
    resultado = await sessao.execute(
        delete(Sessao).where(
            (Sessao.expira_em < limite)
            | (Sessao.encerrada_em.is_not(None) & (Sessao.encerrada_em < limite))
        )
    )
    await sessao.commit()
    return resultado.rowcount or 0


async def tem_provedor_validado(sessao: AsyncSession, usuario_id: UUID) -> bool:
    """Há alguma API de modelos do usuário testada (``validado_em``) e não apagada?"""
    encontrado = await sessao.scalar(
        select(Provedor.id)
        .where(
            Provedor.usuario_id == usuario_id,
            Provedor.validado_em.is_not(None),
            Provedor.apagado_em.is_(None),
        )
        .limit(1)
    )
    return encontrado is not None


async def dados_da_conta(sessao: AsyncSession, usuario_id: UUID) -> tuple[Usuario, bool]:
    """Usuário e se já conectou (e validou) alguma API de modelos."""
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise ErroCredenciais("Conta não encontrada.")
    return usuario, await tem_provedor_validado(sessao, usuario_id)


def apagar_arquivos_do_usuario(raiz: Path, usuario_id: UUID, caminhos: Sequence[str]) -> None:
    """Apaga os anexos (``anexos.caminho`` é relativo ao volume) e a pasta do usuário inteira
    (``<raiz>/<usuario_id>``: anexos e ``cadeias/``). Síncrono: chamar com ``to_thread``.

    Cada caminho passa por ``caminho_do_anexo``: um valor adulterado no banco não apaga nada
    fora do volume.
    """
    for caminho in caminhos:
        try:
            caminho_do_anexo(raiz, caminho).unlink(missing_ok=True)
        except CaminhoInseguro:
            continue
    try:
        pasta = dentro_da_pasta(raiz, raiz / str(usuario_id))
    except CaminhoInseguro:
        return
    if pasta.is_dir():
        shutil.rmtree(pasta)


async def _apagar_checkpoints(sessao: AsyncSession, threads: list[str]) -> None:
    """Apaga o histórico do LangGraph das threads do usuário (se o worker já criou as tabelas)."""
    if not threads:
        return
    for tabela in TABELAS_CHECKPOINT:
        if await sessao.scalar(text("select to_regclass(:t)"), {"t": tabela}) is None:
            continue
        await sessao.execute(
            text(f"delete from {tabela} where thread_id = any(:threads)"),
            {"threads": threads},
        )


def _quebra_ciclo(fk: ForeignKey) -> bool:
    """FK criada depois das tabelas (``use_alter``): existe para fechar um ciclo entre tabelas."""
    return bool(fk.use_alter or (fk.constraint is not None and fk.constraint.use_alter))


def _tabelas_do_banco() -> list[Table]:
    """Todas as tabelas do modelo, pais antes dos filhos (``sorted_tables``)."""
    from app.canais_empresa import tabelas as _canais_empresa  # noqa: F401 - registra no metadata
    from app.modelos import tabelas as _tabelas  # noqa: F401

    return list(Base.metadata.sorted_tables)


TABELAS_SEM_DONO = frozenset({"usuarios", "convites"})
"""Tabelas que não pertencem a um usuário (``convites`` é do sistema)."""


def condicoes_do_usuario(usuario_id: UUID) -> dict[Table, ColumnElement[bool]]:
    """Para cada tabela, a condição SQL que acha as linhas que pertencem ao usuário.

    Derivada das chaves estrangeiras, não de uma lista escrita à mão: uma linha é do usuário se
    aponta para ``usuarios`` ou para uma linha (de outra tabela) que é do usuário. Tabela nova
    entra sozinha; ``test_apagar_conta_cobre_todas_as_tabelas`` falha se alguma ficar sem dono.
    As FKs que só quebram ciclos (``use_alter``) não contam: elas são zeradas antes.
    """
    tabelas = _tabelas_do_banco()
    usuarios = Base.metadata.tables["usuarios"]
    condicoes: dict[Table, ColumnElement[bool]] = {}
    for tabela in tabelas:
        if tabela.name in TABELAS_SEM_DONO:
            continue
        partes: list[ColumnElement[bool]] = []
        for fk in sorted(tabela.foreign_keys, key=lambda f: f.parent.name):
            if _quebra_ciclo(fk):
                continue
            alvo = fk.column.table
            if alvo is usuarios:
                partes.append(fk.parent == usuario_id)
            elif alvo is not tabela and alvo in condicoes:
                partes.append(fk.parent.in_(select(fk.column).where(condicoes[alvo])))
        if partes:
            condicoes[tabela] = or_(*partes)
    return condicoes


async def apagar_linhas_do_usuario(sessao: AsyncSession, usuario_id: UUID) -> None:
    """Apaga, no banco, tudo o que é do usuário e o próprio usuário (sem commit).

    1. zera as FKs que fecham ciclos (``agentes.cadeia_id``, ``mensagens_canal.tarefa_id``…);
    2. apaga os filhos antes dos pais (ordem inversa de ``sorted_tables``);
    3. apaga o usuário.
    """
    condicoes = condicoes_do_usuario(usuario_id)
    for tabela, condicao in condicoes.items():
        for fk in tabela.foreign_keys:
            if _quebra_ciclo(fk):
                await sessao.execute(update(tabela).where(condicao).values({fk.parent.name: None}))
    for tabela in reversed(list(condicoes)):
        await sessao.execute(delete(tabela).where(condicoes[tabela]))
    await sessao.execute(delete(Usuario).where(Usuario.id == usuario_id))


async def apagar_conta(
    sessao: AsyncSession,
    usuario_id: UUID,
    senha: str,
    *,
    redis: Redis | None = None,
    raiz_arquivos: Path | None = None,
) -> None:
    """Apaga tudo do usuário (LGPD), depois de confirmar a senha: banco, checkpoints do
    LangGraph, streams de eventos no Redis e arquivos do volume."""
    from app.agentes.checkpointer import thread_da_conversa, thread_da_etapa
    from app.core.config import obter_configuracao

    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise ErroCredenciais("Conta não encontrada.")
    chave_limite = f"apagar_conta:{usuario_id}"
    if redis is not None:
        espera, membro = await reservar_vaga(redis, chave_limite, *LIMITE_APAGAR_CONTA)
        if espera:
            raise ErroLimite(espera)
    if not await seguranca.verificar_senha_em_thread(senha, usuario.senha_hash):
        raise ErroSenhaIncorreta()
    if redis is not None:
        await devolver_vaga(redis, chave_limite, membro)

    caminhos: Sequence[str] = (
        await sessao.scalars(select(Anexo.caminho).where(Anexo.usuario_id == usuario_id))
    ).all()

    conversas = select(Conversa.id).where(Conversa.usuario_id == usuario_id)
    cadeias = select(Cadeia.id).where(Cadeia.usuario_id == usuario_id)
    etapas = select(Etapa.id).where(Etapa.cadeia_id.in_(cadeias))

    ids_conversas: list[UUID] = list((await sessao.scalars(conversas)).all())
    ids_etapas: list[UUID] = list((await sessao.scalars(etapas)).all())
    await _apagar_checkpoints(
        sessao,
        [thread_da_conversa(c) for c in ids_conversas] + [thread_da_etapa(e) for e in ids_etapas],
    )
    await apagar_linhas_do_usuario(sessao, usuario_id)
    # Commit ANTES de apagar Redis e arquivos: se o banco falhar, nada irreversível foi feito;
    # se o processo cair depois, sobram só arquivos órfãos, nunca uma conta sem arquivos.
    await sessao.commit()
    await revogar_acessos(redis, usuario_id=usuario_id)
    if redis is not None:
        await redis.delete(chave_limite)

    # Redis e arquivos depois do banco: uma falha aqui não deixa a conta pela metade.
    if redis is not None:
        canais = [canal_conversa(c) for c in ids_conversas] + [canal_usuario(usuario_id)]
        await redis.delete(*canais)
    raiz = raiz_arquivos if raiz_arquivos is not None else obter_configuracao().pasta_arquivos
    await asyncio.to_thread(apagar_arquivos_do_usuario, raiz, usuario_id, caminhos)

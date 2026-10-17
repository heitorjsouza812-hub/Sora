"""Regras de contas e sessões; especificação §8.2.

Funções puras (`classificar_token`, `cliente_da_requisicao`) ficam separadas das que falam com o
banco para poderem ser testadas sem PostgreSQL.
"""

import asyncio
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import Select, delete, func, select, text, update
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
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import CadastroEntrada, LoginEntrada
from app.modelos.tabelas import (
    Agente,
    Anexo,
    Aprovacao,
    Cadeia,
    ChamadaModelo,
    Conversa,
    Convite,
    Entrega,
    Etapa,
    Evidencia,
    Memoria,
    Mensagem,
    ModeloDisponivel,
    Passo,
    Pergunta,
    Provedor,
    RegistroAcao,
    RegraPermissao,
    Roteamento,
    Sessao,
    TokenEmail,
    Usuario,
)

CABECALHO_CLIENTE = "X-Sora-Cliente"
CLIENTE_WEB = "web"
CLIENTE_DESKTOP = "desktop"

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
) -> Literal["valido", "reutilizado", "invalido"]:
    """Decide o que fazer com um token de renovação apresentado.

    `reutilizado`: é o token anterior da sessão, já trocado — sinal de roubo (§8.2).
    """
    if sessao is None or sessao.encerrada_em is not None or sessao.expira_em <= agora:
        return "invalido"
    if sessao.token_hash == token_hash:
        return "valido"
    if sessao.anterior_hash == token_hash:
        return "reutilizado"
    return "invalido"


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
        email=email, nome=dados.nome.strip(), senha_hash=seguranca.gerar_hash_senha(dados.senha)
    )
    sessao.add(usuario)
    try:
        await sessao.flush()
    except IntegrityError as erro:  # dois cadastros simultâneos com o mesmo e-mail
        raise ErroEmailEmUso() from erro
    sessao.add(Agente(usuario_id=usuario.id, tipo=TipoAgente.SORA, nome="Sora", cor="#E2ECFF"))
    await sessao.flush()


async def _abrir_sessao(
    sessao: AsyncSession, usuario_id: UUID, cliente: str, ip: str | None, agente_usuario: str | None
) -> tuple[str, str]:
    token, token_hash = seguranca.gerar_token_renovacao()
    sessao.add(
        Sessao(
            usuario_id=usuario_id,
            token_hash=token_hash,
            cliente=cliente,
            expira_em=datetime.now(UTC) + seguranca.RENOVACAO_VALIDADE,
            ip=ip,
            agente_usuario=agente_usuario,
        )
    )
    await sessao.flush()
    return token, seguranca.criar_token_acesso({"sub": str(usuario_id)})


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
    senha_ok = seguranca.verificar_senha(
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
        (Sessao.token_hash == token_hash) | (Sessao.anterior_hash == token_hash)
    )
    return consulta.with_for_update() if travar else consulta


async def _sessao_do_token(
    sessao: AsyncSession, token_hash: str, *, travar: bool = False
) -> Sessao | None:
    return await sessao.scalar(consulta_sessao_do_token(token_hash, travar=travar))


async def renovar(sessao: AsyncSession, token: str | None) -> tuple[str, str, str]:
    """Troca o token de renovação por um novo. Devolve (novo token, acesso, cliente da sessão).

    Token já trocado que reaparece encerra a sessão inteira. A linha fica travada
    (``FOR UPDATE``) até o fim da transação: duas renovações simultâneas com o mesmo token não
    passam as duas; a segunda vê o token como anterior e conta como reuso (API-06/VAL-09).
    """
    if not token:
        raise ErroCredenciais("Sessão expirada. Entre de novo.")
    token_hash = seguranca.hash_token(token)
    existente = await _sessao_do_token(sessao, token_hash, travar=True)
    agora = datetime.now(UTC)
    veredito = classificar_token(existente, token_hash, agora)
    if veredito == "reutilizado" and existente is not None:
        existente.encerrada_em = agora
        await sessao.commit()  # o encerramento precisa sobreviver ao erro que sai daqui
    if veredito != "valido" or existente is None:
        raise ErroCredenciais("Sessão expirada. Entre de novo.")
    novo, novo_hash = seguranca.gerar_token_renovacao()
    existente.anterior_hash = existente.token_hash
    existente.token_hash = novo_hash
    existente.expira_em = agora + seguranca.RENOVACAO_VALIDADE
    await sessao.flush()
    acesso = seguranca.criar_token_acesso({"sub": str(existente.usuario_id)})
    return novo, acesso, existente.cliente


async def sair(sessao: AsyncSession, token: str | None) -> None:
    """Encerra a sessão do token (atual ou anterior). Idempotente."""
    if not token:
        return
    existente = await _sessao_do_token(sessao, seguranca.hash_token(token))
    if existente is not None and existente.encerrada_em is None:
        existente.encerrada_em = datetime.now(UTC)
        await sessao.flush()


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
    if not seguranca.verificar_senha(senha, usuario.senha_hash):
        raise ErroSenhaIncorreta()
    if redis is not None:
        await devolver_vaga(redis, chave_limite, membro)

    caminhos: Sequence[str] = (
        await sessao.scalars(select(Anexo.caminho).where(Anexo.usuario_id == usuario_id))
    ).all()

    conversas = select(Conversa.id).where(Conversa.usuario_id == usuario_id)
    cadeias = select(Cadeia.id).where(Cadeia.usuario_id == usuario_id)
    etapas = select(Etapa.id).where(Etapa.cadeia_id.in_(cadeias))
    mensagens = select(Mensagem.id).where(Mensagem.conversa_id.in_(conversas))
    agentes = select(Agente.id).where(Agente.usuario_id == usuario_id)
    provedores = select(Provedor.id).where(Provedor.usuario_id == usuario_id)

    ids_conversas: list[UUID] = list((await sessao.scalars(conversas)).all())
    ids_etapas: list[UUID] = list((await sessao.scalars(etapas)).all())
    await _apagar_checkpoints(
        sessao,
        [thread_da_conversa(c) for c in ids_conversas] + [thread_da_etapa(e) for e in ids_etapas],
    )

    await sessao.execute(
        update(Agente).where(Agente.usuario_id == usuario_id).values(cadeia_id=None)
    )
    passos_do_usuario = delete(Passo).where(
        (Passo.etapa_id.in_(etapas)) | (Passo.agente_id.in_(agentes))
    )
    for comando in (
        delete(RegistroAcao).where(RegistroAcao.usuario_id == usuario_id),
        delete(Aprovacao).where(Aprovacao.usuario_id == usuario_id),
        delete(RegraPermissao).where(RegraPermissao.usuario_id == usuario_id),
        delete(Evidencia).where(Evidencia.usuario_id == usuario_id),
        delete(Memoria).where(Memoria.usuario_id == usuario_id),
        delete(Pergunta).where(Pergunta.conversa_id.in_(conversas)),
        delete(ChamadaModelo).where(ChamadaModelo.usuario_id == usuario_id),
        delete(Entrega).where(Entrega.usuario_id == usuario_id),
        passos_do_usuario,
        delete(Etapa).where(Etapa.cadeia_id.in_(cadeias)),
        delete(Cadeia).where(Cadeia.usuario_id == usuario_id),
        delete(Roteamento).where(Roteamento.mensagem_id.in_(mensagens)),
        delete(Mensagem).where(Mensagem.conversa_id.in_(conversas)),
        delete(Conversa).where(Conversa.usuario_id == usuario_id),
        delete(Agente).where(Agente.usuario_id == usuario_id),
        delete(ModeloDisponivel).where(ModeloDisponivel.provedor_id.in_(provedores)),
        delete(Provedor).where(Provedor.usuario_id == usuario_id),
        delete(Anexo).where(Anexo.usuario_id == usuario_id),
        delete(TokenEmail).where(TokenEmail.usuario_id == usuario_id),
        delete(Sessao).where(Sessao.usuario_id == usuario_id),
        delete(Usuario).where(Usuario.id == usuario_id),
    ):
        await sessao.execute(comando)
    # Commit ANTES de apagar Redis e arquivos: se o banco falhar, nada irreversível foi feito;
    # se o processo cair depois, sobram só arquivos órfãos, nunca uma conta sem arquivos.
    await sessao.commit()
    if redis is not None:
        await redis.delete(chave_limite)

    # Redis e arquivos depois do banco: uma falha aqui não deixa a conta pela metade.
    if redis is not None:
        canais = [canal_conversa(c) for c in ids_conversas] + [canal_usuario(usuario_id)]
        await redis.delete(*canais)
    raiz = raiz_arquivos if raiz_arquivos is not None else obter_configuracao().pasta_arquivos
    await asyncio.to_thread(apagar_arquivos_do_usuario, raiz, usuario_id, caminhos)

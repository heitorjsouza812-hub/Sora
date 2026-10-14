"""Regras de contas e sessões; especificação §8.2.

Funções puras (`classificar_token`, `cliente_da_requisicao`) ficam separadas das que falam com o
banco para poderem ser testadas sem PostgreSQL.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.redis import verificar_limite
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

LIMITE_LOGIN_EMAIL = (5, 15 * 60)
LIMITE_LOGIN_IP = (20, 15 * 60)
LIMITE_CADASTRO_IP = (5, 60 * 60)

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


async def cadastrar(
    sessao: AsyncSession, redis: Redis, dados: CadastroEntrada, ip: str | None
) -> None:
    """Cria a conta (e a Sora dela) consumindo um convite; na fase 1 o convite é obrigatório."""
    await _limitar(redis, f"cadastro:ip:{ip}", LIMITE_CADASTRO_IP)
    email = normalizar_email(dados.email)
    if not dados.convite:
        raise ErroConvite()
    if await sessao.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        raise ErroEmailEmUso()
    consumido = await sessao.execute(
        update(Convite)
        .where(Convite.codigo == dados.convite, Convite.usos_restantes > 0)
        .values(usos_restantes=Convite.usos_restantes - 1)
        .returning(Convite.codigo)
    )
    if consumido.first() is None:
        raise ErroConvite()
    usuario = Usuario(
        email=email, nome=dados.nome.strip(), senha_hash=seguranca.gerar_hash_senha(dados.senha)
    )
    sessao.add(usuario)
    await sessao.flush()
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
    """Autentica; devolve (token de renovação, token de acesso)."""
    email = normalizar_email(dados.email)
    await _limitar(redis, f"login:email:{email}", LIMITE_LOGIN_EMAIL)
    await _limitar(redis, f"login:ip:{ip}", LIMITE_LOGIN_IP)
    usuario = await sessao.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    senha_ok = seguranca.verificar_senha(
        dados.senha, usuario.senha_hash if usuario else _HASH_FALSO
    )
    if usuario is None or not senha_ok:
        raise ErroCredenciais()
    return await _abrir_sessao(sessao, usuario.id, cliente, ip, agente_usuario)


async def _sessao_do_token(sessao: AsyncSession, token_hash: str) -> Sessao | None:
    return await sessao.scalar(
        select(Sessao).where(
            (Sessao.token_hash == token_hash) | (Sessao.anterior_hash == token_hash)
        )
    )


async def renovar(sessao: AsyncSession, token: str | None) -> tuple[str, str, str]:
    """Troca o token de renovação por um novo. Devolve (novo token, acesso, cliente da sessão).

    Token já trocado que reaparece encerra a sessão inteira.
    """
    if not token:
        raise ErroCredenciais("Sessão expirada. Entre de novo.")
    token_hash = seguranca.hash_token(token)
    existente = await _sessao_do_token(sessao, token_hash)
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


async def dados_da_conta(sessao: AsyncSession, usuario_id: UUID) -> tuple[Usuario, bool]:
    """Usuário e se já conectou alguma API de modelos."""
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise ErroCredenciais("Conta não encontrada.")
    tem_provedor = await sessao.scalar(
        select(Provedor.id).where(Provedor.usuario_id == usuario_id, Provedor.apagado_em.is_(None))
    )
    return usuario, tem_provedor is not None


def _apagar_arquivos(caminhos: Sequence[str]) -> None:
    for caminho in caminhos:
        Path(caminho).unlink(missing_ok=True)


async def apagar_conta(sessao: AsyncSession, usuario_id: UUID, senha: str) -> None:
    """Apaga tudo do usuário (LGPD), depois de confirmar a senha."""
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise ErroCredenciais("Conta não encontrada.")
    if not seguranca.verificar_senha(senha, usuario.senha_hash):
        raise ErroSenhaIncorreta()

    caminhos: Sequence[str] = (
        await sessao.scalars(select(Anexo.caminho).where(Anexo.usuario_id == usuario_id))
    ).all()

    conversas = select(Conversa.id).where(Conversa.usuario_id == usuario_id)
    cadeias = select(Cadeia.id).where(Cadeia.usuario_id == usuario_id)
    etapas = select(Etapa.id).where(Etapa.cadeia_id.in_(cadeias))
    mensagens = select(Mensagem.id).where(Mensagem.conversa_id.in_(conversas))
    agentes = select(Agente.id).where(Agente.usuario_id == usuario_id)
    provedores = select(Provedor.id).where(Provedor.usuario_id == usuario_id)

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
    await sessao.flush()
    # arquivos depois do banco: uma falha aqui não deixa a conta pela metade
    await asyncio.to_thread(_apagar_arquivos, caminhos)

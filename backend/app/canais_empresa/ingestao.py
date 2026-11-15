"""Entrada dos webhooks: normaliza o payload de cada canal, mascara e grava (idempotente).

Só os canais escolhidos pelo usuário entram: Slack pelo id do canal, WhatsApp pelo
``phone_number_id``. Mensagem de bot, edição, exclusão e tipos que não são texto são ignorados.
A máscara de PII roda aqui, antes de gravar qualquer coisa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.pii import mascarar_pii
from app.canais_empresa.tabelas import ConexaoCanalEmpresa, ContatoEmpresa, MensagemEmpresa

registro = logging.getLogger(__name__)

LIMITE_TEXTO = 4_000


@dataclass(frozen=True, slots=True)
class MensagemNormalizada:
    canal: str
    id_externo: str
    canal_externo: str
    fio: str
    contato_externo: str
    contato_nome: str
    papel: str  # cliente | funcionario
    direcao: str  # entrada | saida
    texto: str
    enviada_em: datetime
    link: str | None = None


def _instante(valor: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(valor), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(UTC)


def link_slack(config: dict[str, Any], canal: str, ts: str) -> str:
    dominio = str(config.get("dominio") or "")
    if dominio:
        return f"https://{dominio}.slack.com/archives/{canal}/p{ts.replace('.', '')}"
    equipe = str(config.get("team_id") or "")
    return f"https://app.slack.com/client/{equipe}/{canal}" if equipe else ""


def slack_e_funcionario(
    carga: dict[str, Any], evento: dict[str, Any], config: dict[str, Any], usuario: str
) -> bool:
    """Quem escreve no Slack é cliente até prova em contrário (a prova vem do dono):

    - só os ids em ``config["ids_funcionarios"]`` entram como funcionário na hora;
    - quem é de **outro workspace** (Slack Connect: ``user_team`` diferente do workspace) é
      cliente, mesmo que alguém tenha posto o id na lista;
    - convidados e membros reais são conferidos depois, com ``users.info``
      (``workers.canais_empresa``): membro pleno do workspace vira funcionário, convidado
      (``is_restricted``) e externo (``is_stranger``) continuam cliente.
    """
    workspace = str(config.get("team_id") or carga.get("team_id") or "")
    time_do_autor = str(evento.get("user_team") or "")
    if workspace and time_do_autor and time_do_autor != workspace:
        return False
    return usuario in (config.get("ids_funcionarios") or [])


def normalizar_slack(
    carga: dict[str, Any], config: dict[str, Any], escolhidos: list[str]
) -> list[MensagemNormalizada]:
    """Evento ``message`` da Events API. Ignora o que não é texto novo de uma pessoa."""
    if carga.get("type") != "event_callback":
        return []
    evento = carga.get("event")
    if not isinstance(evento, dict) or evento.get("type") != "message":
        return []
    if evento.get("subtype") or evento.get("bot_id"):
        return []
    canal, usuario, ts = evento.get("channel"), evento.get("user"), evento.get("ts")
    texto = evento.get("text")
    if not (isinstance(canal, str) and isinstance(usuario, str) and isinstance(ts, str)):
        return []
    if not isinstance(texto, str) or not texto.strip() or canal not in escolhidos:
        return []
    if usuario == config.get("bot_user_id"):
        return []
    funcionario = slack_e_funcionario(carga, evento, config, usuario)
    fio_ref = str(evento.get("thread_ts") or canal)
    return [
        MensagemNormalizada(
            canal="slack",
            id_externo=f"{canal}:{ts}",
            canal_externo=canal,
            fio=f"slack:{canal}:{fio_ref}",
            contato_externo=usuario,
            contato_nome="",
            papel="funcionario" if funcionario else "cliente",
            direcao="saida" if funcionario else "entrada",
            texto=texto,
            enviada_em=_instante(ts),
            link=link_slack(config, canal, ts) or None,
        )
    ]


def _texto_whatsapp(msg: dict[str, Any]) -> str:
    tipo = msg.get("type")
    if tipo == "text":
        return str((msg.get("text") or {}).get("body") or "")
    corpo = msg.get(tipo) if isinstance(tipo, str) else None
    if isinstance(corpo, dict) and tipo in {"image", "video", "document"}:
        return str(corpo.get("caption") or "")
    return ""


def normalizar_whatsapp(carga: dict[str, Any], escolhidos: list[str]) -> list[MensagemNormalizada]:
    """Mensagens recebidas (``messages``) e, no modo de coexistência, as enviadas pelo app do
    celular da empresa (``smb_message_echoes``), que viram mensagens do funcionário."""
    if carga.get("object") != "whatsapp_business_account":
        return []
    saida: list[MensagemNormalizada] = []
    for entrada in carga.get("entry") or []:
        for mudanca in (entrada.get("changes") or []) if isinstance(entrada, dict) else []:
            valor = mudanca.get("value") if isinstance(mudanca, dict) else None
            if not isinstance(valor, dict):
                continue
            numero_id = str((valor.get("metadata") or {}).get("phone_number_id") or "")
            if numero_id not in escolhidos:
                continue
            nomes = {
                str(c.get("wa_id")): str((c.get("profile") or {}).get("name") or "")
                for c in valor.get("contacts") or []
                if isinstance(c, dict)
            }
            for msg in valor.get("messages") or []:
                if not isinstance(msg, dict):
                    continue
                texto, origem, mid = _texto_whatsapp(msg), str(msg.get("from") or ""), msg.get("id")
                if texto.strip() and origem and isinstance(mid, str):
                    saida.append(
                        MensagemNormalizada(
                            canal="whatsapp",
                            id_externo=mid,
                            canal_externo=numero_id,
                            fio=f"whatsapp:{numero_id}:{origem}",
                            contato_externo=origem,
                            contato_nome=nomes.get(origem, ""),
                            papel="cliente",
                            direcao="entrada",
                            texto=texto,
                            enviada_em=_instante(msg.get("timestamp")),
                        )
                    )
            for eco in valor.get("message_echoes") or []:
                if not isinstance(eco, dict):
                    continue
                texto, cliente, mid = _texto_whatsapp(eco), str(eco.get("to") or ""), eco.get("id")
                if texto.strip() and cliente and isinstance(mid, str):
                    saida.append(
                        MensagemNormalizada(
                            canal="whatsapp",
                            id_externo=mid,
                            canal_externo=numero_id,
                            fio=f"whatsapp:{numero_id}:{cliente}",
                            contato_externo=cliente,
                            contato_nome=nomes.get(cliente, ""),
                            papel="cliente",
                            direcao="saida",
                            texto=texto,
                            enviada_em=_instante(eco.get("timestamp")),
                        )
                    )
    return saida


async def registrar_mensagens(
    sessao: AsyncSession, conexao: ConexaoCanalEmpresa, mensagens: list[MensagemNormalizada]
) -> list[tuple[UUID, UUID]]:
    """Grava contatos e mensagens (já mascaradas). Devolve ``[(contato_id, mensagem_id)]`` só das
    mensagens novas: reentrega do mesmo id de mensagem não grava nada."""
    novas: list[tuple[UUID, UUID]] = []
    for m in mensagens:
        texto = mascarar_pii(m.texto.strip())[:LIMITE_TEXTO]
        if not texto:
            continue
        inserir_contato = insert(ContatoEmpresa).values(
            usuario_id=conexao.usuario_id,
            conexao_id=conexao.id,
            canal=m.canal,
            id_externo=m.contato_externo,
            nome=m.contato_nome,
            papel=m.papel,
            ultima_mensagem_em=m.enviada_em,
        )
        contato_id = await sessao.scalar(
            inserir_contato.on_conflict_do_update(
                index_elements=["conexao_id", "id_externo"],
                set_={
                    "nome": func.coalesce(
                        func.nullif(ContatoEmpresa.nome, ""), inserir_contato.excluded.nome
                    ),
                    "ultima_mensagem_em": func.greatest(
                        ContatoEmpresa.ultima_mensagem_em,
                        inserir_contato.excluded.ultima_mensagem_em,
                    ),
                },
            ).returning(ContatoEmpresa.id)
        )
        mensagem_id = await sessao.scalar(
            insert(MensagemEmpresa)
            .values(
                usuario_id=conexao.usuario_id,
                conexao_id=conexao.id,
                contato_id=contato_id,
                id_externo=m.id_externo,
                canal_externo=m.canal_externo,
                fio=m.fio,
                direcao=m.direcao,
                texto=texto,
                link=m.link,
                enviada_em=m.enviada_em,
            )
            .on_conflict_do_nothing(index_elements=["conexao_id", "id_externo"])
            .returning(MensagemEmpresa.id)
        )
        if mensagem_id is not None:
            novas.append((contato_id, mensagem_id))
    return novas

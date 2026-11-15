"""Ferramentas dos bots para os canais da empresa. As duas só LEEM, e só para bots (ou grupos)
que o usuário autorizou:

- ``consultar_cliente``: a ficha de um cliente (preferências, pedidos, promessas, prazos…);
- ``consultar_conhecimento``: a base de conhecimento da empresa (FAQ, produtos, políticas…).

Não existe ferramenta de resposta ao cliente: a Sora não envia nada por esses canais. O texto
devolvido vem de mensagens de terceiros, então sai cercado como dado externo.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.canais_empresa import acesso
from app.canais_empresa import conhecimento as base
from app.canais_empresa.tabelas import ContatoEmpresa, FatoCliente
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao

ROTULO_DO_TIPO = {
    "preferencia": "Preferências",
    "pedido": "Pedidos",
    "promessa": "Promessas feitas",
    "prazo": "Prazos",
    "reclamacao": "Reclamações",
    "dado_de_contato": "Contato",
}


class ConsultarCliente(BaseModel):
    """Consulta a ficha de um cliente da empresa (preferências, pedidos, promessas, prazos e
    reclamações lidos do WhatsApp e do Slack). Só funciona se o usuário autorizou você. Informe
    o nome ou o telefone do cliente. É só leitura."""

    cliente: str = Field(min_length=2, max_length=120)


class ConsultarConhecimento(BaseModel):
    """Busca na base de conhecimento da empresa (perguntas frequentes e boas respostas, produtos
    e preços, políticas de troca e entrega, processos, tom de voz, objeções). Só funciona se o
    usuário autorizou você. É só leitura."""

    consulta: str = Field(min_length=2, max_length=300)
    categoria: Literal["faq", "produto", "politica", "processo", "tom_de_voz", "objecao"] | None = (
        None
    )


def _cercado(texto: str, origem: str) -> str:
    from app.agentes.prompts import cercar

    return cercar(texto, origem)


async def _checar(sessao, contexto: ContextoFerramenta, escopo: str) -> None:
    if not await acesso.autorizado(
        sessao,
        contexto.usuario_id,
        escopo,
        agente_id=contexto.agente_id,
        grupo_id=contexto.canal_id,
    ):
        raise ErroFerramenta(acesso.SEM_AUTORIZACAO)


async def consultar_cliente(args: ConsultarCliente, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        await _checar(sessao, contexto, "clientes")
        busca = args.cliente.strip()
        digitos = re.sub(r"\D", "", busca)
        condicoes = [ContatoEmpresa.nome.ilike(f"%{busca}%")]
        if len(digitos) >= 6:
            condicoes.append(ContatoEmpresa.id_externo.contains(digitos))
        contatos = list(
            (
                await sessao.scalars(
                    select(ContatoEmpresa)
                    .where(
                        ContatoEmpresa.usuario_id == contexto.usuario_id,
                        ContatoEmpresa.papel == "cliente",
                        or_(*condicoes),
                    )
                    .order_by(ContatoEmpresa.ultima_mensagem_em.desc().nulls_last())
                    .limit(4)
                )
            ).all()
        )
        if not contatos:
            return "Nenhum cliente encontrado com esse nome ou telefone."
        if len(contatos) > 1:
            nomes = ", ".join(c.nome or c.id_externo for c in contatos)
            return _cercado(
                f"Mais de um cliente combina: {nomes}. Peça um nome mais completo ou o telefone.",
                "clientes_encontrados",
            )
        contato = contatos[0]
        fatos = list(
            (
                await sessao.scalars(
                    select(FatoCliente)
                    .where(
                        FatoCliente.contato_id == contato.id,
                        FatoCliente.usuario_id == contexto.usuario_id,
                    )
                    .order_by(FatoCliente.tipo, FatoCliente.criado_em)
                )
            ).all()
        )
    if not fatos:
        return _cercado(
            f"{contato.nome or contato.id_externo}: ainda não há fatos na ficha.",
            "ficha_do_cliente",
        )
    linhas = [f"Ficha de {contato.nome or contato.id_externo} ({contato.canal}):"]
    for tipo, rotulo in ROTULO_DO_TIPO.items():
        itens = [f for f in fatos if f.tipo == tipo]
        if not itens:
            continue
        linhas.append(f"{rotulo}:")
        for f in itens:
            data = f" (data: {f.data_referencia.isoformat()})" if f.data_referencia else ""
            origem = f" [origem: {f.origem_link}]" if f.origem_link else ""
            linhas.append(f"- {f.texto}{data}{origem}")
    return _cercado("\n".join(linhas), "ficha_do_cliente")


async def consultar_conhecimento(args: ConsultarConhecimento, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        await _checar(sessao, contexto, "conhecimento")
        itens = await base.buscar(
            sessao,
            contexto.usuario_id,
            args.consulta,
            categoria=args.categoria,
            limite=5,
            so_do_prompt=True,
        )
        texto = "\n".join(base.texto_do_item(i) for i in itens)
    if not texto:
        return "A base de conhecimento da empresa não tem nada sobre isso."
    return _cercado(texto, "conhecimento_da_empresa")


async def bloco_de_conhecimento(sessao, contexto) -> str:
    """Trecho do prompt de um bot autorizado: o que a empresa mais repete e o **usuário aprovou**
    (política e FAQ), cercado como dado. Vazio se o bot não está autorizado ou não há nada.
    Item novo, contraditório ou só de cliente não entra (``condicoes_do_prompt``)."""
    from sqlalchemy import desc

    from app.canais_empresa.tabelas import ConhecimentoEmpresa

    if not await acesso.autorizado(
        sessao, contexto.usuario_id, "conhecimento", agente_id=contexto.agente_id
    ):
        return ""
    itens = list(
        (
            await sessao.scalars(
                select(ConhecimentoEmpresa)
                .where(
                    ConhecimentoEmpresa.usuario_id == contexto.usuario_id,
                    *base.condicoes_do_prompt(),
                )
                .order_by(
                    desc(ConhecimentoEmpresa.ocorrencias), desc(ConhecimentoEmpresa.ultima_em)
                )
                .limit(5)
            )
        ).all()
    )
    if not itens:
        return ""
    corpo = "\n".join(base.texto_do_item(i) for i in itens)
    return (
        "Conhecimento da empresa que mais aparece nos atendimentos (use ``consultar_conhecimento`` "
        "para buscar mais):\n" + _cercado(corpo, "conhecimento_da_empresa")
    )

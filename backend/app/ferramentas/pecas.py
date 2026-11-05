"""Executores das ferramentas das peças do Rakazo (Âncora, etapa 4).

Os esquemas e as regras puras ficam nos módulos de cada peça (``app/memoria``,
``app/pendencias``, ``app/habilidades``, ``app/ferramentas/historico`` …); aqui cada ferramenta
ganha a função ``async def nome(args, contexto)`` que o registro chama, abrindo a própria sessão
no banco (como as ferramentas da fase 1). Nada aqui decide aprovação: o cartão de
``propor_instrucoes``, ``esquecer_memoria`` e ``apagar_habilidade`` vem do middleware do revisor
(``app/revisor/execucao.py``) *antes* de a função rodar.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import Agente, Conversa, Habilidade, Mensagem
from app.modelos.tabelas import Pendencia as LinhaPendencia

# ---------------------------------------------------------------- memória


async def _servico_memoria(sessao: Any, usuario_id: UUID) -> Any:
    from app.memoria.servico import ArmazemMemoriasSQL, ServicoMemoria
    from app.memoria.vetorizador import vetorizador_do_usuario

    return ServicoMemoria(
        ArmazemMemoriasSQL(sessao), await vetorizador_do_usuario(sessao, usuario_id)
    )


async def lembrar(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        servico = await _servico_memoria(sessao, contexto.usuario_id)
        registro = await servico.lembrar(contexto.usuario_id, contexto.agente_id, args.conteudo)
    return f"Memória guardada (id: {registro.id})."


async def buscar_memoria(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        servico = await _servico_memoria(sessao, contexto.usuario_id)
        registros = await servico.buscar(contexto.usuario_id, contexto.agente_id, args.consulta)
    return servico.contexto(registros) or "Nenhuma memória encontrada."


async def esquecer_memoria(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        servico = await _servico_memoria(sessao, contexto.usuario_id)
        apagou = await servico.esquecer(contexto.usuario_id, args.memoria_id)
    return "Memória apagada." if apagou else "Não encontrei essa memória."


# ---------------------------------------------------------------- histórico


async def buscar_historico(args: Any, contexto: ContextoFerramenta) -> str:
    from app.ferramentas.historico import buscar_em_mensagens, carregar_mensagens

    async with abrir_sessao() as sessao:
        mensagens = await carregar_mensagens(sessao, contexto.usuario_id, contexto.conversa_id)
    return json.dumps(buscar_em_mensagens(mensagens, args), ensure_ascii=False, default=str)


async def ler_historico(args: Any, contexto: ContextoFerramenta) -> str:
    from app.ferramentas.historico import carregar_mensagens, ler_em_mensagens

    async with abrir_sessao() as sessao:
        mensagens = await carregar_mensagens(sessao, contexto.usuario_id, contexto.conversa_id)
    return json.dumps(ler_em_mensagens(mensagens, args), ensure_ascii=False, default=str)


# ---------------------------------------------------------------- catálogo de tarefas


async def catalogo_tarefas(args: Any, contexto: ContextoFerramenta) -> str:
    from app.agentes.montagem import FERRAMENTAS_POR_PAPEL
    from app.ferramentas.catalogo_tarefas import montar_catalogo
    from app.ferramentas.registro import ESQUEMAS, esquemas_das_proximas_fases
    from app.modelos.tabelas import Rotina
    from app.pendencias import listar_do_banco

    async with abrir_sessao() as sessao:
        agente = await sessao.get(Agente, contexto.agente_id)
        papel = _papel(agente)
        nomes = list(
            dict.fromkeys(
                [*FERRAMENTAS_POR_PAPEL.get(papel, ()), *(agente.ferramentas if agente else [])]
            )
        )
        habilidades = (
            await sessao.execute(
                select(Habilidade.nome, Habilidade.descricao)
                .where(Habilidade.usuario_id == contexto.usuario_id)
                .order_by(Habilidade.nome)
            )
        ).all()
        pendencias = await listar_do_banco(sessao, contexto.usuario_id, contexto.agente_id)
        rotinas = (
            await sessao.scalars(
                select(Rotina).where(
                    Rotina.usuario_id == contexto.usuario_id,
                    Rotina.agente_id == contexto.agente_id,
                    Rotina.ativa.is_(True),
                )
            )
        ).all()
    esquemas = ESQUEMAS | esquemas_das_proximas_fases()
    catalogo = montar_catalogo(
        ferramentas=[
            (n, (esquemas[n].__doc__ or n).strip() if n in esquemas else n) for n in nomes
        ],
        habilidades=[(h.nome, h.descricao) for h in habilidades],
        agendamentos=[
            {"id": str(r.id), "titulo": r.titulo, "tipo": r.tipo, "expressao": r.expressao}
            for r in rotinas
        ],
        pendencias=[{"id": str(p.id), "titulo": p.titulo, "status": p.status} for p in pendencias],
    )
    return json.dumps(catalogo, ensure_ascii=False, default=str)


def _papel(agente: Agente | None) -> str:
    from app.modelos.enumeracoes import TipoAgente

    if agente is None:
        return "individual"
    if agente.tipo == TipoAgente.SORA:
        return "sora"
    if agente.tipo == TipoAgente.INDIVIDUAL:
        return "individual"
    return agente.papel or "redator"


# ---------------------------------------------------------------- instruções


async def propor_instrucoes(args: Any, contexto: ContextoFerramenta) -> str:
    """Só chega aqui depois do cartão aprovado (política ``cartao_fixo``). Grava as instruções."""
    async with abrir_sessao() as sessao:
        agente = await sessao.get(Agente, contexto.agente_id)
        if agente is None or agente.usuario_id != contexto.usuario_id:
            raise ErroFerramenta("Agente não encontrado.")
        await sessao.execute(
            text("UPDATE agentes SET instrucoes = :t WHERE id = :id").bindparams(
                t=args.instrucoes, id=contexto.agente_id
            )
        )
    return "As novas instruções foram aprovadas e valem a partir do próximo turno."


async def instrucoes_atuais(agente_id: UUID) -> str:
    async with abrir_sessao() as sessao:
        valor = await sessao.scalar(
            text("SELECT instrucoes FROM agentes WHERE id = :id").bindparams(id=agente_id)
        )
    return valor or ""


# ---------------------------------------------------------------- pendências


def _linha_json(p: LinhaPendencia) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "titulo": p.titulo,
        "notas": p.notas,
        "status": p.status,
        "atualizada_em": p.atualizada_em.isoformat() if p.atualizada_em else None,
    }


async def adicionar_pendencia(args: Any, contexto: ContextoFerramenta) -> str:
    from app.pendencias import MAX_PENDENCIAS_ABERTAS, STATUS_ABERTOS, nova_pendencia

    async with abrir_sessao() as sessao:
        abertas = await sessao.scalar(
            select(func.count())
            .select_from(LinhaPendencia)
            .where(
                LinhaPendencia.usuario_id == contexto.usuario_id,
                LinhaPendencia.agente_id == contexto.agente_id,
                LinhaPendencia.status.in_(STATUS_ABERTOS),
            )
        )
        nova = nova_pendencia(contexto.usuario_id, contexto.agente_id, args, abertas or 0)
        if (abertas or 0) >= MAX_PENDENCIAS_ABERTAS:
            raise ErroFerramenta("Muitas pendências abertas.")
        sessao.add(
            LinhaPendencia(
                id=nova.id,
                usuario_id=nova.usuario_id,
                agente_id=nova.agente_id,
                titulo=nova.titulo,
                notas=nova.notas,
                status=nova.status,
            )
        )
    return f"Pendência anotada (id: {nova.id})."


async def listar_pendencias(args: Any, contexto: ContextoFerramenta) -> str:
    from app.pendencias import STATUS_ABERTOS

    async with abrir_sessao() as sessao:
        consulta = select(LinhaPendencia).where(
            LinhaPendencia.usuario_id == contexto.usuario_id,
            LinhaPendencia.agente_id == contexto.agente_id,
        )
        if not args.incluir_concluidas:
            consulta = consulta.where(LinhaPendencia.status.in_(STATUS_ABERTOS))
        linhas = (
            await sessao.scalars(consulta.order_by(LinhaPendencia.atualizada_em.desc()).limit(100))
        ).all()
    return json.dumps({"pendencias": [_linha_json(p) for p in linhas]}, ensure_ascii=False)


async def _pendencia_do_agente(sessao: Any, contexto: ContextoFerramenta, pid: UUID) -> Any:
    linha = await sessao.scalar(
        select(LinhaPendencia).where(
            LinhaPendencia.id == pid,
            LinhaPendencia.usuario_id == contexto.usuario_id,
            LinhaPendencia.agente_id == contexto.agente_id,
        )
    )
    if linha is None:
        raise ErroFerramenta("Pendência não encontrada.")
    return linha


async def atualizar_pendencia(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        linha = await _pendencia_do_agente(sessao, contexto, args.pendencia_id)
        if args.titulo is None and args.notas is None and args.status is None:
            raise ErroFerramenta("Nada para atualizar.")
        if args.titulo is not None:
            linha.titulo = args.titulo.strip()
        if args.notas is not None:
            linha.notas = args.notas.strip()
        if args.status is not None:
            linha.status = args.status
        linha.atualizada_em = datetime.now(UTC)
    return "Pendência atualizada."


async def concluir_pendencia(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        linha = await _pendencia_do_agente(sessao, contexto, args.pendencia_id)
        linha.status = "concluida"
        linha.atualizada_em = datetime.now(UTC)
    return "Pendência concluída."


async def remover_pendencia(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        linha = await _pendencia_do_agente(sessao, contexto, args.pendencia_id)
        await sessao.delete(linha)
    return "Pendência removida."


# ---------------------------------------------------------------- habilidades


async def _habilidade(sessao: Any, usuario_id: UUID, nome: str) -> Habilidade | None:
    return await sessao.scalar(
        select(Habilidade).where(
            Habilidade.usuario_id == usuario_id, func.lower(Habilidade.nome) == nome.strip().lower()
        )
    )


async def ler_habilidade(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        linha = await _habilidade(sessao, contexto.usuario_id, args.nome)
    if linha is None:
        raise ErroFerramenta(f"Não existe a habilidade {args.nome}. Use catalogo_tarefas.")
    return linha.conteudo


async def criar_habilidade(args: Any, contexto: ContextoFerramenta) -> str:
    from app.habilidades import montar_skill_md

    conteudo = montar_skill_md(args.nome, args.descricao, args.corpo)
    async with abrir_sessao() as sessao:
        if await _habilidade(sessao, contexto.usuario_id, args.nome) is not None:
            raise ErroFerramenta(
                "Já existe uma habilidade com esse nome. Use atualizar_habilidade."
            )
        sessao.add(
            Habilidade(
                id=uuid4(),
                usuario_id=contexto.usuario_id,
                nome=args.nome.strip(),
                descricao=args.descricao.strip(),
                conteudo=conteudo,
                origem="agente",
            )
        )
    return f"Habilidade {args.nome.strip()} criada."


async def atualizar_habilidade(args: Any, contexto: ContextoFerramenta) -> str:
    from app.habilidades import ler_skill_md, montar_skill_md

    async with abrir_sessao() as sessao:
        linha = await _habilidade(sessao, contexto.usuario_id, args.nome)
        if linha is None:
            raise ErroFerramenta("Habilidade não encontrada.")
        if linha.origem == "sistema":
            raise ErroFerramenta("Habilidades do sistema não podem ser alteradas.")
        atual = ler_skill_md(linha.conteudo)
        descricao = (args.descricao if args.descricao is not None else atual.descricao).strip()
        corpo = args.corpo if args.corpo is not None else atual.corpo
        linha.conteudo = montar_skill_md(linha.nome, descricao, corpo, atual.frontmatter)
        linha.descricao = descricao
        linha.atualizada_em = datetime.now(UTC)
    return "Habilidade atualizada."


async def apagar_habilidade(args: Any, contexto: ContextoFerramenta) -> str:
    async with abrir_sessao() as sessao:
        linha = await _habilidade(sessao, contexto.usuario_id, args.nome)
        if linha is None:
            raise ErroFerramenta("Habilidade não encontrada.")
        if linha.origem == "sistema":
            raise ErroFerramenta("Habilidades do sistema não podem ser apagadas.")
        await sessao.delete(linha)
    return "Habilidade apagada."


# ---------------------------------------------------------------- enviar_para_agente


async def enviar_para_agente(args: Any, contexto: ContextoFerramenta) -> str:
    from app.ferramentas.enviar_para_agente import preparar_envio
    from workers.fila import enfileirar

    async with abrir_sessao() as sessao:
        colegas = set(
            await sessao.scalars(
                select(Agente.id).where(
                    Agente.usuario_id == contexto.usuario_id,
                    Agente.apagado_em.is_(None),
                    Agente.id != contexto.agente_id,
                )
            )
        )
        # Salto da última mensagem recebida nesta conversa (o usuário zera a corrente).
        salto_origem = await sessao.scalar(
            select(Mensagem.salto)
            .where(Mensagem.conversa_id == contexto.conversa_id, Mensagem.visivel.is_(True))
            .order_by(Mensagem.criada_em.desc())
            .limit(1)
        )
        envio = preparar_envio(
            args,
            contexto,
            salto_de_origem=salto_origem,
            colegas=colegas,
            chamada_id=uuid4().hex,
        )
        conversa_destino = await sessao.scalar(
            select(Conversa)
            .where(
                Conversa.usuario_id == contexto.usuario_id,
                Conversa.agente_id == envio.para_agente_id,
            )
            .order_by(Conversa.atualizada_em.desc())
            .limit(1)
        )
        if conversa_destino is None:
            raise ErroFerramenta("Esse agente ainda não tem uma conversa para receber a mensagem.")
        mensagem = Mensagem(
            id=uuid4(),
            conversa_id=conversa_destino.id,
            autor=AutorMensagem.AGENTE,
            agente_id=contexto.agente_id,
            conteudo=envio.texto,
            responde_a=envio.responde_a,
            salto=envio.salto,
            visivel=True,
        )
        sessao.add(mensagem)
        mensagem_id = mensagem.id
    await enfileirar(
        "responder_direto", id_job=f"entrega:{mensagem_id}", mensagem_id=str(mensagem_id)
    )
    return "Mensagem enviada. Siga com o que não depende da resposta."

"""Job de resposta direta (especificação §2, "O que acontece num POST
/mensagens", passos 3 e 5; §6, ``responder_direto``).

Resposta no modo ``direto`` (N1 ou N2) ou num agente individual: o agente roda com as
ferramentas reais e fala pela ferramenta ``falar`` (que grava a mensagem e emite
``mensagem.inicio/delta/fim``). Se o modelo respondeu em texto puro, sem chamar ``falar``, o
worker fala por ele. Termina com ``sugestoes``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import func, select, text

from app.agentes.ferramentas_do_turno import superficie_do_pedido
from app.eventos.streams import publicar_evento
from app.eventos.tipos import SugestoesEvento
from app.filas import FilaAgente, OrigemItem
from app.filas.sql import ArmazemFilaSQL
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.modelos.enumeracoes import AutorMensagem, TipoAgente
from app.modelos.tabelas import Agente, Conversa, Mensagem
from app.orquestrador.modelos import SemModeloDisponivel
from app.preferencias_conversa import (
    ModeloEscolhidoIndisponivel,
    escolha_efetiva,
    texto_da_falha,
)

registro = logging.getLogger(__name__)


def _texto_do_conteudo(conteudo: Any) -> str:
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, list):  # blocos (Anthropic, Gemini): só os de texto
        return "\n".join(
            str(bloco.get("text", "")).strip()
            for bloco in conteudo
            if isinstance(bloco, dict) and bloco.get("type") == "text" and bloco.get("text")
        ).strip()
    return ""


def _texto_da_resposta(resultado: dict[str, Any]) -> str:
    """Texto puro com que o modelo terminou ESTE turno (Engrenagem).

    Só vale a última mensagem, se for do modelo e sem chamada de ferramenta. Antes a busca voltava
    pelo histórico inteiro: um turno que terminava sem texto (resposta vazia, ou retomada depois
    de um cartão) achava a resposta de um turno anterior e o worker a mandava de novo, duplicada.
    """
    mensagens = resultado.get("messages") or []
    if not mensagens:
        return ""
    ultima = mensagens[-1]
    if not isinstance(ultima, AIMessage) or ultima.tool_calls:
        return ""
    return _texto_do_conteudo(ultima.content)


def _normalizar(texto: str) -> str:
    return " ".join(texto.split()).casefold()


def _texto_final_depois_de_trabalho(resultado: dict[str, Any], texto: str) -> bool:
    """O turno já falou, mas só como aviso: depois do último ``falar`` vieram outras ferramentas e
    o modelo terminou a resposta em texto puro, que se perdia (decisão do Heitor, 2026-11-18).

    Fica de fora o texto que vem logo depois de um ``falar`` sem trabalho no meio (sobra do tipo
    "Pronto, mandei acima") e o que repete a última fala. Olha só o turno atual (desde a última
    mensagem do usuário).
    """
    mensagens = resultado.get("messages") or []
    inicio = max((i for i, m in enumerate(mensagens) if isinstance(m, HumanMessage)), default=-1)
    ultimo_falar = ultimo_trabalho = -1
    ultima_fala = ""
    for i, m in enumerate(mensagens[inicio + 1 :], start=inicio + 1):
        if isinstance(m, AIMessage):
            for chamada in m.tool_calls or []:
                if chamada.get("name") == "falar":
                    ultima_fala = str((chamada.get("args") or {}).get("texto") or "")
        elif isinstance(m, ToolMessage):
            if m.name == "falar":
                ultimo_falar = i
            else:
                ultimo_trabalho = i
    if ultimo_falar < 0:
        return False
    if _normalizar(texto) in _normalizar(ultima_fala):
        return False
    # Sem trabalho entre a fala e o texto, só passa o que a fala anunciou ("Segue a lista:"); o
    # resto é sobra do tipo "Pronto, mandei acima".
    return ultimo_trabalho > ultimo_falar or ultima_fala.rstrip().endswith(":")


async def responder_direto(ctx: dict[str, Any], mensagem_id: str) -> None:
    """Põe o pedido na fila persistida do agente e manda despachar. Quem roda o turno é
    ``executar_item_fila`` (workers/equipe.py), para que a 2ª mensagem a um agente ocupado, a
    fila retomada e o "Repetir" também sejam respondidos."""
    async with ctx["sessoes"]() as sessao:
        mensagem = await sessao.get(Mensagem, UUID(mensagem_id))
        conversa = await sessao.get(Conversa, mensagem.conversa_id) if mensagem else None
        if mensagem is None or conversa is None:
            return
        fila = FilaAgente(ArmazemFilaSQL(sessao))
        item = await fila.enfileirar(
            usuario_id=conversa.usuario_id,
            agente_id=conversa.agente_id,
            texto=mensagem.conteudo,
            origem=OrigemItem.USUARIO,
            anexos=(UUID(a) for a in mensagem.anexos),
            chave=f"conversa:{mensagem.id}",
        )
        await sessao.commit()
    from workers.fila import enfileirar

    await enfileirar("despachar_equipe", agente_id=str(item.agente_id))


async def rodar_turno_do_item(ctx: dict[str, Any], item: Any) -> None:
    """Roda o agente para um item da fila. Itens de mensagem trazem ``conversa:<id>`` na chave;
    os demais (Repetir, outras origens) usam a conversa mais recente do agente e o texto do item."""
    chave = item.chave or ""
    if chave.startswith("conversa:"):
        await _responder_direto_sem_fila(ctx, chave.split(":", 1)[1])
    else:
        await _responder_direto_sem_fila(
            ctx,
            None,
            agente_id=item.agente_id,
            usuario_id=item.usuario_id,
            texto=item.texto,
            anexos=item.anexos,
            item_id=item.id,
        )


async def _responder_direto_sem_fila(
    ctx: dict[str, Any],
    mensagem_id: str | None,
    *,
    agente_id: UUID | None = None,
    usuario_id: UUID | None = None,
    texto: str | None = None,
    anexos: Any = (),
    item_id: UUID | None = None,
) -> None:
    """Roda a Sora (ou o agente individual) e manda o texto pelos eventos
    ``mensagem.*``, terminando com ``sugestoes``. Quem põe na fila: a API."""
    from app.agentes import ContextoAgente
    from app.agentes.ancora import aplicar_habilidade_forcada
    from app.agentes.visao import preparar_entrada
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar
    from workers.cadeia import dependencias_da_etapa

    async with ctx["sessoes"]() as sessao:
        if mensagem_id is not None:
            mensagem = await sessao.get(Mensagem, UUID(mensagem_id))
            if mensagem is None or mensagem.estado == "interrompida":
                return
            conversa = await sessao.get(Conversa, mensagem.conversa_id)
            texto = mensagem.conteudo
        else:
            conversa = await sessao.scalar(
                select(Conversa)
                .where(Conversa.usuario_id == usuario_id, Conversa.agente_id == agente_id)
                .order_by(Conversa.atualizada_em.desc())
                .limit(1)
            )
        agente = await sessao.get(Agente, conversa.agente_id) if conversa else None
        if conversa is None or agente is None or texto is None:
            return
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        usuario_id, conversa_id, agente_id = conversa.usuario_id, conversa.id, agente.id
        # Seletor do campo de mensagem: modelo e raciocínio desta conversa (ou do bot).
        escolha = await escolha_efetiva(
            sessao, usuario_id, conversa_id=conversa_id, agente_id=agente_id
        )
        # Anexos do usuário chegam ao modelo: lista de arquivos e, com modelo de visão, as imagens.
        try:
            entrada_usuario, modelos = await preparar_entrada(
                sessao,
                conversa.usuario_id,
                texto,
                mensagem.anexos if mensagem_id is not None else anexos,
                papel,
                dificuldade=1,
                conversa_privada=conversa.privada,
                precisa_visao=any(f.startswith("computador_") for f in agente.ferramentas or []),
                escolha=escolha,
            )
        except ModeloEscolhidoIndisponivel as erro:
            indisponivel = str(erro)
        except SemModeloDisponivel:
            indisponivel = "Conecte um modelo com ferramentas em Configurações → Modelos de IA."
        else:
            indisponivel = None
        antes = await _falas_do_bot(sessao, conversa_id)
        historico = list(
            (
                await sessao.scalars(
                    select(Mensagem)
                    .where(Mensagem.conversa_id == conversa_id, Mensagem.visivel.is_(True))
                    .order_by(Mensagem.criada_em, Mensagem.id)
                )
            ).all()
        )
        if mensagem_id is not None:
            posicao = next((i for i, m in enumerate(historico) if str(m.id) == mensagem_id), 0)
            historico = historico[:posicao]
    if indisponivel is not None:
        # O modelo escolhido sumiu: avisa e não troca sozinho.
        await falar(
            Falar(texto=indisponivel),
            ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id),
        )
        await publicar_evento(
            ctx["redis_eventos"], SugestoesEvento(itens=[]), conversa_id, usuario_id
        )
        return

    contexto = ContextoAgente(
        usuario_id=usuario_id,
        agente_id=agente_id,
        conversa_id=conversa_id,
        papel=papel,
        superficie=superficie_do_pedido(texto),
        valores_do_prompt={"perfil_do_agente": agente.papel} if papel == "individual" else {},
        ferramentas_do_bot=list(agente.ferramentas or []),
        ferramentas_extras=list(agente.ferramentas or []),
        # Item sem mensagem (Repetir): thread só dele. Na thread da conversa cada execução
        # acrescentava o histórico inteiro de novo (mensagens sem id), e o pedido ao modelo dobrava.
        thread_proprio=f"conversa:{conversa_id}:pedido:{mensagem_id or item_id}"
        if (mensagem_id or item_id)
        else None,
        dependencias=dependencias_da_etapa(ctx, usuario_id=usuario_id, conversa_id=conversa_id),
    )
    if modelo_falso_ativo() and not any(
        gatilho in texto for gatilho in ("[aprovacao]", "[pergunta]", "[grupo]")
    ):
        # O roteiro da Sora falsa chama ``falar`` em ciclo para servir outros fluxos do agente.
        # Com ``[aprovacao]``, ``[pergunta]`` ou ``[grupo]`` o agente roda de verdade e abre o
        # cartão (aprovação fixa, pergunta ou proposta de grupo).
        # Na resposta direta basta uma resposta textual, enviada pela ferramenta real.
        resposta_falsa = await criar_modelo_falso("resposta_direta").ainvoke([HumanMessage(texto)])
        await falar(
            Falar(texto=str(resposta_falsa.content)),
            ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id),
        )
        await publicar_evento(
            ctx["redis_eventos"], SugestoesEvento(itens=[]), conversa_id, usuario_id
        )
        await _talvez_aprender(ctx, contexto)
        return
    texto_final = await aplicar_habilidade_forcada(usuario_id, texto)
    if texto_final != texto:
        entrada_usuario = entrada_usuario.com_texto(texto, texto_final)
    for aviso in entrada_usuario.avisos:
        # Ex.: modelo sem visão. O aviso é uma mensagem do bot; conta como fala antes do turno.
        await falar(
            Falar(texto=aviso),
            ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id),
        )
        antes = (antes or 0) + 1
    await _rodar_e_falar(
        ctx,
        contexto,
        modelos,
        antes=antes,
        entrada={
            "messages": [
                HumanMessage(m.conteudo)
                if m.autor == AutorMensagem.USUARIO
                else AIMessage(m.conteudo)
                for m in historico
            ]
            + [HumanMessage(entrada_usuario.conteudo)]
        },
    )


MENSAGEM_FALHA = (
    "Não consegui terminar essa resposta agora (o modelo de IA não respondeu). "
    "Tente de novo em instantes ou confira o provedor em Configurações → Modelos de IA."
)


async def _abrir_turno_vivo(conversa_id: Any) -> str | None:
    """Marca a conversa como "respondendo agora": a API passa a aceitar "Mandar agora".
    Falha no Redis não impede o turno (a mensagem do usuário só cai na fila normal)."""
    from app.ferramentas import ambiente

    marca = uuid4().hex
    try:
        await ambiente.marcar_turno_vivo(conversa_id, marca)
    except Exception:
        registro.warning("não consegui marcar o turno vivo da conversa", exc_info=True)
        return None
    return marca


async def _fechar_turno_vivo(conversa_id: Any, marca: str | None) -> None:
    """Tira a marca e manda pela fila normal o que chegou depois da última chamada ao modelo
    (senão essas mensagens ficariam sem resposta)."""
    if marca is None:
        return
    from app.ferramentas import ambiente
    from workers.fila import enfileirar

    try:
        await ambiente.desmarcar_turno_vivo(conversa_id, marca)
        sobras = await ambiente.esvaziar_correio_do_turno(conversa_id)
    except Exception:
        registro.warning("não consegui fechar o turno vivo da conversa", exc_info=True)
        return
    for item in sobras:
        if item["mensagem_id"]:
            await enfileirar(
                "responder_direto",
                id_job=f"responder:{item['mensagem_id']}",
                mensagem_id=item["mensagem_id"],
            )


async def _falas_do_bot(sessao: Any, conversa_id: Any) -> int:
    """Quantas mensagens da conversa NÃO são do usuário. É assim que o worker sabe se o bot já
    falou no turno; contar as do usuário enganaria a conta quando ele manda algo com "Mandar
    agora" no meio da resposta."""
    total = await sessao.scalar(
        select(func.count())
        .select_from(Mensagem)
        .where(Mensagem.conversa_id == conversa_id, Mensagem.autor != AutorMensagem.USUARIO)
    )
    return int(total or 0)


async def _ultima_etapa(ctx: dict[str, Any], contexto: Any) -> str:
    from app.ferramentas.rotulos import NOME_EXIBIDO

    thread = getattr(contexto, "thread_proprio", None)
    if thread and ctx.get("checkpointer"):
        try:
            estado = await ctx["checkpointer"].aget({"configurable": {"thread_id": thread}})
        except Exception:
            registro.warning("Última etapa indisponível ao relatar uma falha do turno")
            return ""
        mensagens = (estado or {}).get("channel_values", {}).get("messages", ())
        for m in reversed(mensagens):
            if isinstance(m, HumanMessage):
                break
            if isinstance(m, ToolMessage) and m.name and m.name != "falar":
                etapa = {
                    "navegador_abrir": "abrir a página",
                    "navegador_observar": "ler os elementos da página",
                    "navegador_procurar": "localizar um elemento na página",
                    "navegador_acao": "agir no elemento da página",
                    "computador_abrir_programa": "abrir o programa",
                    "computador_agir": "executar a ação no computador",
                }.get(m.name, NOME_EXIBIDO.get(m.name))
                if etapa:
                    return f"Última etapa com retorno: {etapa}. "
    return ""


async def _pedido_de_equipe(contexto: Any, entrada: dict[str, Any] | None) -> tuple[str, int]:
    """Texto do pedido e quantos cartões de bot/grupo já existem, se este turno é um pedido de
    bot ou de grupo feito à Sora; senão ``("", 0)``."""
    if contexto.papel != "sora" or not entrada:
        return "", 0
    from app.sistema1.atalhos_equipe import contar_cartoes, intencao_de_equipe

    mensagens = entrada.get("messages") or []
    texto = str(getattr(mensagens[-1], "content", "")) if mensagens else ""
    if intencao_de_equipe(texto) is None:
        return "", 0
    return texto, await contar_cartoes(contexto.usuario_id)


async def _cartao_de_seguranca(ferramenta: Any, pedido: str, cartoes_antes: int) -> None:
    """O turno acabou (bem ou mal) sem o cartão de bot/grupo que o pedido pedia: prepara-o."""
    if not pedido:
        return
    from app.sistema1.atalhos_equipe import garantir_cartao

    try:
        await garantir_cartao(ferramenta, pedido, cartoes_antes)
    except Exception:
        registro.exception("a rede de segurança do cartão falhou")


async def _rodar_e_falar(
    ctx: dict[str, Any],
    contexto: Any,
    modelos: list[Any],
    *,
    antes: int | None,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
) -> None:
    """Roda (ou retoma) o agente da conversa. Se o modelo respondeu em texto puro, o worker
    fala por ele; se o provedor falhar, a conversa recebe um aviso em PT-BR em vez de ficar muda."""
    from app.agentes import montar_e_rodar_agente
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar

    ferramenta = ContextoFerramenta(
        usuario_id=contexto.usuario_id,
        agente_id=contexto.agente_id,
        conversa_id=contexto.conversa_id,
    )
    pedido_de_equipe, cartoes_antes = await _pedido_de_equipe(contexto, entrada)
    if antes is None:
        # Retomada (cartão ou pergunta): conta agora, para o texto puro do fim só ser falado se o
        # turno retomado não falou nada (antes ele era falado sempre, repetindo o que já saiu).
        async with ctx["sessoes"]() as sessao:
            antes = await _falas_do_bot(sessao, contexto.conversa_id)
    marca = await _abrir_turno_vivo(contexto.conversa_id)
    try:
        # O ARQ cancela o job aos 360 s. Reserve tempo para fechar o turno e avisar pelo SSE.
        async with asyncio.timeout(285):
            resultado = await montar_e_rodar_agente(
                contexto=contexto,
                modelos=modelos,
                checkpointer=ctx["checkpointer"],
                entrada=entrada,
                resposta=resposta,
            )
    except Exception as erro:
        await _fechar_turno_vivo(contexto.conversa_id, marca)
        from app.agentes.middleware.cancelamento import CadeiaCancelada

        if isinstance(erro, CadeiaCancelada):
            return
        from app.llm.limite import mensagem_de_limite

        registro.warning("Conversa %s: %s", contexto.conversa_id, type(erro).__name__)
        from app.agentes.middleware.limites import (
            MENSAGEM_LIMITE_DE_PASSOS,
            estourou_limite_de_passos,
        )

        texto = (
            MENSAGEM_LIMITE_DE_PASSOS
            if estourou_limite_de_passos(erro)
            else texto_da_falha(modelos, erro) or mensagem_de_limite(erro) or MENSAGEM_FALHA
        )
        if isinstance(erro, TimeoutError):
            texto = "O tempo deste turno acabou antes de eu conseguir concluir o pedido."
        await falar(Falar(texto=await _ultima_etapa(ctx, contexto) + texto), ferramenta)
        await _cartao_de_seguranca(ferramenta, pedido_de_equipe, cartoes_antes)
        await publicar_evento(
            ctx["redis_eventos"],
            SugestoesEvento(itens=[]),
            contexto.conversa_id,
            contexto.usuario_id,
        )
        return

    await _fechar_turno_vivo(contexto.conversa_id, marca)
    if not resultado.get("__interrupt__"):
        async with ctx["sessoes"]() as sessao:
            depois = await _falas_do_bot(sessao, contexto.conversa_id)
        texto = _texto_da_resposta(resultado)
        if texto and (
            antes is None or depois == antes or _texto_final_depois_de_trabalho(resultado, texto)
        ):
            # O modelo respondeu em texto puro: o worker fala por ele.
            from app.agentes.middleware.conversa import coletar_fontes, fontes_do_turno

            fontes = []
            for m in resultado.get("messages", []):
                if isinstance(m, ToolMessage) and (
                    m.name in {"buscar_web", "ler_pagina"}
                    or (m.name or "").startswith("navegador_")
                ):
                    coletar_fontes(str(m.content).split("Fontes para citação:")[0], fontes)
            token = fontes_do_turno.set(fontes)
            try:
                await falar(Falar(texto=texto), ferramenta)
            finally:
                fontes_do_turno.reset(token)
        elif depois == antes and not texto:
            # Nem texto nem ferramenta: um provedor que ignora ``stream`` ou devolve vazio deixaria
            # a conversa muda. O usuário recebe o aviso e pode tentar de novo.
            registro.warning(
                "o modelo terminou o turno da conversa %s sem responder", contexto.conversa_id
            )
            await falar(Falar(texto=MENSAGEM_FALHA), ferramenta)
    if not resultado.get("__interrupt__"):
        await _cartao_de_seguranca(ferramenta, pedido_de_equipe, cartoes_antes)
        await _talvez_aprender(ctx, contexto)
    await publicar_evento(
        ctx["redis_eventos"], SugestoesEvento(itens=[]), contexto.conversa_id, contexto.usuario_id
    )


async def _talvez_aprender(ctx: dict[str, Any], contexto: Any) -> None:
    """Onda 3: a cada N mensagens do usuário, o job ``aprender_com_correcoes`` relê a conversa.
    Só conta e enfileira aqui; falha não afeta a resposta que o usuário já recebeu."""
    from app.memoria.aprendizado import precisa_reler
    from workers.fila import enfileirar

    try:
        async with ctx["sessoes"]() as sessao:
            ultima = await precisa_reler(sessao, contexto.usuario_id, contexto.conversa_id)
        if ultima is not None:
            await enfileirar(
                "aprender_com_correcoes",
                id_job=f"aprender:{contexto.conversa_id}:{ultima}",
                conversa_id=str(contexto.conversa_id),
            )
    except Exception:
        registro.warning(
            "não consegui agendar o aprendizado da conversa %s", contexto.conversa_id, exc_info=True
        )


async def retomar_conversa(ctx: dict[str, Any], conversa_id: str, resposta: Any) -> None:
    """Retoma o agente de uma conversa fora de cadeia (Sora ou agente individual) depois que o
    usuário respondeu uma pergunta ou decidiu uma aprovação. Quem põe na fila: a API."""
    from app.agentes.checkpointer import pausa_da_conversa

    if not isinstance(resposta, dict):
        return
    cartao = resposta.get("aprovacao_id") or resposta.get("pergunta_id")
    if not cartao:
        return
    async with ctx["sessoes"]() as trava:
        # Serializa decisões de cartões paralelos da mesma conversa, inclusive jobs repetidos.
        await trava.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:chave, 0))"),
            {"chave": f"retomar:{conversa_id}"},
        )
        for tentativa in range(12):
            pausa = await pausa_da_conversa(
                trava, ctx["checkpointer"], UUID(conversa_id), str(cartao)
            )
            if pausa:
                thread, interrupcao = pausa
                await _retomar_pedido(ctx, conversa_id, resposta, thread, interrupcao)
                return
            # O usuário pode decidir no intervalo entre a emissão do cartão e o checkpoint.
            if tentativa < 11:
                await asyncio.sleep(0.25)
        registro.info("Cartão sem interrupção pendente na conversa %s", conversa_id)
    if 0 < ctx.get("job_try", 0) < 3:
        # O cartão pode ter sido decidido enquanto o worker ainda gravava o checkpoint.
        # Um job duplicado só consulta o estado e termina sem executar o efeito.
        from arq import Retry

        raise Retry(defer=3)


async def _retomar_pedido(
    ctx: dict[str, Any], conversa_id: str, resposta: Any, thread: str, interrupcao: str
) -> None:
    from app.agentes import ContextoAgente
    from app.orquestrador.modelos import modelos_do_papel
    from workers.cadeia import dependencias_da_etapa, valor_da_retomada

    valor = valor_da_retomada(resposta)
    if valor is None:
        return
    async with ctx["sessoes"]() as sessao:
        conversa = await sessao.get(Conversa, UUID(conversa_id))
        agente = await sessao.get(Agente, conversa.agente_id) if conversa else None
        if conversa is None or agente is None:
            return
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        escolha = await escolha_efetiva(
            sessao, conversa.usuario_id, conversa_id=conversa.id, agente_id=agente.id
        )
        try:
            modelos = await modelos_do_papel(
                sessao,
                conversa.usuario_id,
                papel,
                dificuldade=1,
                conversa_privada=conversa.privada,
                escolha=escolha,
            )
        except (ModeloEscolhidoIndisponivel, SemModeloDisponivel) as erro:
            from app.ferramentas.base import ContextoFerramenta
            from app.ferramentas.falar import Falar, falar

            usuario_id, agente_id = conversa.usuario_id, agente.id
            await sessao.commit()
            await falar(
                Falar(
                    texto=(
                        "Conecte um modelo com ferramentas em Configurações → Modelos de IA."
                        if isinstance(erro, SemModeloDisponivel)
                        else str(erro)
                    )
                ),
                ContextoFerramenta(
                    usuario_id=usuario_id, agente_id=agente_id, conversa_id=UUID(conversa_id)
                ),
            )
            return
        usuario_id, agente_id = conversa.usuario_id, agente.id
        pedido = (
            await sessao.get(Mensagem, UUID(thread.rsplit(":", 1)[-1]))
            if ":pedido:" in thread
            else None
        )
        if pedido is not None and (not pedido.visivel or pedido.estado == "interrompida"):
            return
    contexto = ContextoAgente(
        usuario_id=usuario_id,
        agente_id=agente_id,
        conversa_id=UUID(conversa_id),
        papel=papel,
        superficie=superficie_do_pedido(pedido.conteudo) if pedido else None,
        valores_do_prompt={"perfil_do_agente": agente.papel} if papel == "individual" else {},
        ferramentas_do_bot=list(agente.ferramentas or []),
        ferramentas_extras=list(agente.ferramentas or []),
        thread_proprio=thread,
        dependencias=dependencias_da_etapa(
            ctx, usuario_id=usuario_id, conversa_id=UUID(conversa_id)
        ),
    )
    await _rodar_e_falar(ctx, contexto, modelos, antes=None, resposta={interrupcao: valor})

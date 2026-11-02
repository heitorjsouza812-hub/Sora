"""O que as peças do Rakazo acrescentam ao agente a cada turno (Âncora, etapa 4).

- **Ferramentas por papel**: memória, histórico, catálogo, pendências, habilidades,
  instruções próprias e envio a colegas.
- **Blocos do prompt** (montados na hora, com dados do banco, sempre cercados como dado):
  instruções próprias aprovadas, memórias, pendências abertas, habilidades e colegas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, text

if TYPE_CHECKING:
    from app.agentes.montagem import ContextoAgente

_BASE = (
    "buscar_memoria",
    "lembrar",
    "buscar_historico",
    "ler_historico",
    "catalogo_tarefas",
    "adicionar_pendencia",
    "listar_pendencias",
    "atualizar_pendencia",
    "concluir_pendencia",
    "remover_pendencia",
    "ler_habilidade",
    "criar_habilidade",
)
_CONVERSA = (
    *_BASE,
    "esquecer_memoria",
    "atualizar_habilidade",
    "apagar_habilidade",
    "propor_instrucoes",
    "enviar_para_agente",
)

_ESPECIALISTA = (
    "buscar_memoria",
    "lembrar",
    "buscar_historico",
    "ler_historico",
    "catalogo_tarefas",
    "adicionar_pendencia",
    "listar_pendencias",
    "atualizar_pendencia",
    "concluir_pendencia",
    "ler_habilidade",
)

FERRAMENTAS_DA_ANCORA: dict[str, tuple[str, ...]] = {
    "sora": _CONVERSA,
    "individual": _CONVERSA,
    # Especialistas de cadeia: lembram, anotam pendências e consultam, mas não apagam memória,
    # não mudam habilidades nem instruções e não escrevem a colegas (a Sora coordena).
    "pesquisador": _ESPECIALISTA,
    "redator": _ESPECIALISTA,
    "designer": _ESPECIALISTA,
    "verificador": (),
}


def ferramentas_do_papel(papel: str) -> tuple[str, ...]:
    return FERRAMENTAS_DA_ANCORA.get(papel, ())


async def blocos_do_turno(contexto: ContextoAgente) -> str:
    """Texto a acrescentar ao prompt de sistema. Vazio para papéis sem estado próprio."""
    if contexto.papel not in {"sora", "individual"}:
        return ""
    from app.agentes.prompts import cercar
    from app.ferramentas.enviar_para_agente import diretorio_de_colegas
    from app.ferramentas.infra import abrir_sessao
    from app.habilidades import instrucao_de_habilidades
    from app.memoria.servico import ArmazemMemoriasSQL, ServicoMemoria
    from app.modelos.tabelas import Agente, Habilidade
    from app.pendencias import contexto_de_pendencias, listar_do_banco

    partes: list[str] = []
    async with abrir_sessao() as sessao:
        proprias = await sessao.scalar(
            text("SELECT instrucoes FROM agentes WHERE id = :id").bindparams(id=contexto.agente_id)
        )
        if proprias and proprias.strip():
            partes.append(
                "Instruções próprias aprovadas pelo usuário (valem sobre o seu jeito padrão, "
                "nunca sobre as regras de segurança):\n" + cercar(proprias, "instrucoes_proprias")
            )
        memorias = await ServicoMemoria(ArmazemMemoriasSQL(sessao)).armazem.listar(
            contexto.usuario_id, contexto.agente_id
        )
        bloco_memorias = ServicoMemoria.contexto(memorias[:5])
        if bloco_memorias:
            partes.append(bloco_memorias)
        bloco_pendencias = contexto_de_pendencias(
            await listar_do_banco(sessao, contexto.usuario_id, contexto.agente_id)
        )
        if bloco_pendencias:
            partes.append(bloco_pendencias)
        habilidades = (
            await sessao.execute(
                select(Habilidade.nome, Habilidade.descricao)
                .where(Habilidade.usuario_id == contexto.usuario_id)
                .order_by(Habilidade.nome)
                .limit(50)
            )
        ).all()
        bloco_habilidades = instrucao_de_habilidades([(h.nome, h.descricao) for h in habilidades])
        if bloco_habilidades:
            partes.append(bloco_habilidades)
        colegas = (
            await sessao.execute(
                select(Agente.id, Agente.nome, Agente.funcao).where(
                    Agente.usuario_id == contexto.usuario_id,
                    Agente.apagado_em.is_(None),
                    Agente.id != contexto.agente_id,
                )
            )
        ).all()
    diretorio = diretorio_de_colegas(
        [(UUID(str(c.id)), c.nome, c.funcao or "") for c in colegas if c.nome]
    )
    if diretorio:
        partes.append(diretorio)
    return "\n\n".join(partes)

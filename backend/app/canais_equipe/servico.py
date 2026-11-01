"""Regras dos canais de equipe: mensagens, tarefas, delegação e os controles do usuário.

O serviço não chama modelo nem fila: ele decide e grava. O worker lê o que mudou e age
(começa turnos, interrompe os que pararam, manda eventos para a interface).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.canais_equipe.modelos import (
    ABERTAS,
    EM_ANDAMENTO,
    MAX_DELEGACOES_POR_PEDIDO,
    MAX_INSTRUCOES,
    MAX_MEMBROS,
    MAX_NOME_CANAL,
    MAX_PROPOSITO,
    MAX_TAREFAS_RODANDO_POR_CANAL,
    MAX_TEXTO_MENSAGEM,
    AutorCanal,
    Canal,
    ErroCanal,
    MensagemCanal,
    MotivoParada,
    StatusTarefa,
    TarefaCanal,
    TipoMensagemCanal,
)
from app.canais_equipe.roteamento import DecisaoConferida, Membro, Rota, rotear

# ---------- persistência ----------


class ArmazemCanais(Protocol):
    async def canal(self, canal_id: UUID) -> Canal | None: ...
    async def salvar_canal(self, canal: Canal) -> None: ...
    async def canais_do_usuario(self, usuario_id: UUID) -> list[Canal]: ...
    async def proximo_seq(self, canal_id: UUID) -> int: ...
    async def gravar_mensagem(self, mensagem: MensagemCanal) -> None: ...
    async def mensagens(self, canal_id: UUID) -> list[MensagemCanal]: ...
    async def gravar_tarefa(self, tarefa: TarefaCanal) -> None: ...
    async def tarefa(self, tarefa_id: UUID) -> TarefaCanal | None: ...
    async def tarefas(self, canal_id: UUID) -> list[TarefaCanal]: ...
    async def tarefas_abertas(self) -> list[TarefaCanal]: ...


class ArmazemCanaisEmMemoria:
    def __init__(self) -> None:
        self._canais: dict[UUID, Canal] = {}
        self._mensagens: dict[UUID, list[MensagemCanal]] = {}
        self._tarefas: dict[UUID, TarefaCanal] = {}
        self._seq: dict[UUID, itertools.count[int]] = {}

    async def canal(self, canal_id: UUID) -> Canal | None:
        return self._canais.get(canal_id)

    async def salvar_canal(self, canal: Canal) -> None:
        self._canais[canal.id] = canal

    async def canais_do_usuario(self, usuario_id: UUID) -> list[Canal]:
        return [c for c in self._canais.values() if c.usuario_id == usuario_id]

    async def proximo_seq(self, canal_id: UUID) -> int:
        return next(self._seq.setdefault(canal_id, itertools.count(1)))

    async def gravar_mensagem(self, mensagem: MensagemCanal) -> None:
        self._mensagens.setdefault(mensagem.canal_id, []).append(mensagem)

    async def mensagens(self, canal_id: UUID) -> list[MensagemCanal]:
        return sorted(self._mensagens.get(canal_id, []), key=lambda m: m.seq)

    async def gravar_tarefa(self, tarefa: TarefaCanal) -> None:
        self._tarefas[tarefa.id] = tarefa

    async def tarefa(self, tarefa_id: UUID) -> TarefaCanal | None:
        return self._tarefas.get(tarefa_id)

    async def tarefas(self, canal_id: UUID) -> list[TarefaCanal]:
        return sorted(
            (t for t in self._tarefas.values() if t.canal_id == canal_id),
            key=lambda t: t.criada_em,
        )

    async def tarefas_abertas(self) -> list[TarefaCanal]:
        return [t for t in self._tarefas.values() if t.status in ABERTAS]


# ---------- resultados ----------


@dataclass(slots=True)
class Mudancas:
    """O que o worker precisa fazer depois de uma operação."""

    mensagens: list[MensagemCanal] = field(default_factory=list)
    tarefas: list[TarefaCanal] = field(default_factory=list)
    interromper: list[UUID] = field(default_factory=list)
    """Tarefas com turno rodando que precisam ser interrompidas agora."""
    precisa_lider: UUID | None = None
    """Mensagem que o líder precisa rotear (o worker faz o turno curto do líder)."""
    rota: Rota | None = None


def _agora() -> datetime:
    return datetime.now(UTC)


class ServicoCanais:
    def __init__(self, armazem: ArmazemCanais) -> None:
        self._armazem = armazem

    # ---------- canal ----------

    async def criar(
        self,
        *,
        usuario_id: UUID,
        nome: str,
        membros: Sequence[UUID],
        lider_id: UUID | None = None,
        proposito: str = "",
        instrucoes: str = "",
        agentes_do_usuario: set[UUID],
    ) -> Canal:
        canal = Canal(id=uuid4(), usuario_id=usuario_id, nome="")
        self._aplicar_config(
            canal, nome, membros, lider_id, proposito, instrucoes, agentes_do_usuario
        )
        await self._armazem.salvar_canal(canal)
        return canal

    async def configurar(
        self,
        canal_id: UUID,
        usuario_id: UUID,
        *,
        nome: str,
        membros: Sequence[UUID],
        lider_id: UUID | None,
        proposito: str,
        instrucoes: str,
        agentes_do_usuario: set[UUID],
    ) -> Mudancas:
        canal = await self._do_usuario(canal_id, usuario_id)
        antigos = set(canal.membros)
        lider_antigo = canal.lider_id
        self._aplicar_config(
            canal, nome, membros, lider_id, proposito, instrucoes, agentes_do_usuario
        )
        await self._armazem.salvar_canal(canal)
        mudancas = Mudancas()
        sairam = antigos - set(canal.membros)
        for tarefa in await self._armazem.tarefas(canal.id):
            if tarefa.dono_id in sairam and tarefa.status in EM_ANDAMENTO:
                if tarefa.status is StatusTarefa.RODANDO:
                    mudancas.interromper.append(tarefa.id)
                self._parar(tarefa, MotivoParada.DONO_SAIU)
                await self._armazem.gravar_tarefa(tarefa)
                mudancas.tarefas.append(tarefa)
        if canal.lider_id is not None and canal.lider_id != lider_antigo:
            mudancas.mensagens.append(
                await self._atividade(canal, "Novo líder do canal.", agente_id=canal.lider_id)
            )
        return mudancas

    def _aplicar_config(
        self,
        canal: Canal,
        nome: str,
        membros: Sequence[UUID],
        lider_id: UUID | None,
        proposito: str,
        instrucoes: str,
        agentes_do_usuario: set[UUID],
    ) -> None:
        nome = " ".join(nome.split())
        if not 1 <= len(nome) <= MAX_NOME_CANAL:
            raise ErroCanal(f"O nome do canal precisa ter de 1 a {MAX_NOME_CANAL} caracteres.")
        membros = list(dict.fromkeys(membros))
        if not membros:
            raise ErroCanal("Escolha pelo menos um agente para o canal.")
        if len(membros) > MAX_MEMBROS:
            raise ErroCanal(f"Um canal tem no máximo {MAX_MEMBROS} agentes.")
        if not set(membros) <= agentes_do_usuario:
            raise ErroCanal("Só dá para pôr no canal agentes da sua conta.")
        if lider_id is not None and lider_id not in membros:
            raise ErroCanal("O líder precisa ser um dos membros do canal.")
        if len(proposito) > MAX_PROPOSITO or len(instrucoes) > MAX_INSTRUCOES:
            raise ErroCanal("Propósito ou instruções longos demais.")
        canal.nome = nome
        canal.membros = membros
        canal.lider_id = lider_id
        canal.proposito = proposito.strip()
        canal.instrucoes = instrucoes.strip()

    async def arquivar(self, canal_id: UUID, usuario_id: UUID) -> Mudancas:
        """Para todo o trabalho e guarda o canal (na interface: "Apagar", com Restaurar)."""
        canal = await self._do_usuario(canal_id, usuario_id)
        mudancas = Mudancas()
        if canal.arquivado:
            return mudancas
        for tarefa in await self._armazem.tarefas(canal.id):
            if tarefa.status in EM_ANDAMENTO:
                if tarefa.status is StatusTarefa.RODANDO:
                    mudancas.interromper.append(tarefa.id)
                self._parar(tarefa, None)
                await self._armazem.gravar_tarefa(tarefa)
                mudancas.tarefas.append(tarefa)
        canal.arquivado_em = _agora()
        await self._armazem.salvar_canal(canal)
        return mudancas

    async def restaurar(self, canal_id: UUID, usuario_id: UUID) -> Mudancas:
        """O canal volta a aceitar mensagens. O trabalho parado fica esperando "Retomar"."""
        canal = await self._do_usuario(canal_id, usuario_id)
        mudancas = Mudancas()
        if not canal.arquivado:
            return mudancas
        canal.arquivado_em = None
        await self._armazem.salvar_canal(canal)
        for tarefa in await self._armazem.tarefas(canal.id):
            if tarefa.status is StatusTarefa.PARADA and tarefa.motivo is None:
                tarefa.motivo = MotivoParada.CANAL_ARQUIVADO
                await self._armazem.gravar_tarefa(tarefa)
                mudancas.tarefas.append(tarefa)
        return mudancas

    # ---------- mensagens do usuário ----------

    async def mensagem_do_usuario(
        self,
        canal_id: UUID,
        usuario_id: UUID,
        *,
        texto: str,
        membros: Sequence[Membro],
        destinatario: UUID | None = None,
        responde_a: UUID | None = None,
        anexos: Sequence[UUID] = (),
    ) -> Mudancas:
        canal = await self._do_usuario(canal_id, usuario_id)
        if canal.arquivado:
            raise ErroCanal("Este canal está arquivado. Restaure para mandar mensagens.")
        texto = texto.strip()
        if not texto and not anexos:
            raise ErroCanal("A mensagem está vazia.")
        if len(texto) > MAX_TEXTO_MENSAGEM:
            raise ErroCanal("Mensagem longa demais; mande como anexo.")
        membros = [m for m in membros if m.id in canal.membros]
        historico = {m.id: m for m in await self._armazem.mensagens(canal.id)}
        if responde_a is not None and responde_a not in historico:
            raise ErroCanal("A mensagem respondida não é deste canal.")
        tarefas = await self._armazem.tarefas(canal.id)
        rota = rotear(
            texto=texto,
            membros=membros,
            lider_id=canal.lider_id,
            tarefas=tarefas,
            mensagens=historico,
            destinatario=destinatario,
            responde_a=responde_a,
        )
        mensagem = MensagemCanal(
            id=uuid4(),
            canal_id=canal.id,
            seq=await self._armazem.proximo_seq(canal.id),
            autor=AutorCanal.USUARIO,
            texto=texto,
            responde_a=responde_a,
            anexos=tuple(anexos),
        )
        await self._armazem.gravar_mensagem(mensagem)
        mudancas = Mudancas(mensagens=[mensagem], rota=rota)
        await self._aplicar_rota(canal, mensagem, rota, tarefas, mudancas)
        return mudancas

    async def _aplicar_rota(
        self,
        canal: Canal,
        mensagem: MensagemCanal,
        rota: Rota,
        tarefas: Sequence[TarefaCanal],
        mudancas: Mudancas,
    ) -> None:
        por_id = {t.id: t for t in tarefas}
        if rota.tipo == "donos":
            for agente_id in rota.agentes:
                tarefa = TarefaCanal(
                    id=uuid4(),
                    canal_id=canal.id,
                    pedido_id=mensagem.id,
                    dono_id=agente_id,
                    instrucao=rota.texto or mensagem.texto,
                    raiz_id=uuid4(),
                )
                tarefa.raiz_id = tarefa.id
                await self._armazem.gravar_tarefa(tarefa)
                mudancas.tarefas.append(tarefa)
                if not rota.determinista and agente_id != canal.lider_id:
                    mudancas.mensagens.append(
                        await self._atividade(
                            canal,
                            "O líder passou o pedido para este agente.",
                            agente_id=agente_id,
                            tarefa_id=tarefa.id,
                        )
                    )
        elif rota.tipo == "seguimento":
            for tarefa_id in rota.tarefas:
                tarefa = por_id[tarefa_id]
                tarefa.seguimentos.append(mensagem.id)
                if tarefa.status in (StatusTarefa.PARADA, StatusTarefa.FALHOU):
                    self._reabrir(tarefa, await self._tem_filhas_abertas(tarefa))
                tarefa.atualizada_em = _agora()
                await self._armazem.gravar_tarefa(tarefa)
                mudancas.tarefas.append(tarefa)
        elif rota.tipo == "retomar":
            for tarefa_id in rota.tarefas:
                for tarefa in await self._reabrir_arvore(por_id[tarefa_id], canal):
                    if tarefa.id == tarefa_id:
                        tarefa.seguimentos.append(mensagem.id)
                        await self._armazem.gravar_tarefa(tarefa)
                    mudancas.tarefas.append(tarefa)
        elif rota.tipo == "lider":
            mudancas.precisa_lider = mensagem.id
        else:  # sem_lider
            canal.pedidos_sem_lider.append(mensagem.id)
            await self._armazem.salvar_canal(canal)
            mudancas.mensagens.append(
                await self._atividade(
                    canal,
                    "Não sei para quem mandar: escolha um líder para o canal ou mencione um "
                    "agente com @.",
                )
            )

    async def pedidos_para_rotear_com_lider(self, canal_id: UUID, usuario_id: UUID) -> list[UUID]:
        """Depois de escolher um líder: as mensagens que esperavam por ele (e esvazia a lista)."""
        canal = await self._do_usuario(canal_id, usuario_id)
        if canal.lider_id is None:
            return []
        pendentes, canal.pedidos_sem_lider = canal.pedidos_sem_lider, []
        await self._armazem.salvar_canal(canal)
        return pendentes

    async def decisao_do_lider(
        self, canal_id: UUID, usuario_id: UUID, mensagem_id: UUID, conferida: DecisaoConferida
    ) -> Mudancas:
        canal = await self._do_usuario(canal_id, usuario_id)
        mensagens = {m.id: m for m in await self._armazem.mensagens(canal.id)}
        mensagem = mensagens.get(mensagem_id)
        if mensagem is None:
            raise ErroCanal("Mensagem não encontrada neste canal.")
        mudancas = Mudancas(mensagens=[], rota=conferida.rota)
        if canal.arquivado or conferida.sem_resposta:
            return mudancas
        if conferida.pergunta:
            assert canal.lider_id is not None
            pergunta = MensagemCanal(
                id=uuid4(),
                canal_id=canal.id,
                seq=await self._armazem.proximo_seq(canal.id),
                autor=AutorCanal.AGENTE,
                agente_id=canal.lider_id,
                texto=conferida.pergunta,
                responde_a=mensagem.id,
            )
            await self._armazem.gravar_mensagem(pergunta)
            mudancas.mensagens.append(pergunta)
            return mudancas
        if conferida.ilegivel or conferida.rota is None or canal.lider_id is None:
            dono = canal.lider_id or canal.membros[0]
            tarefa = TarefaCanal(
                id=uuid4(),
                canal_id=canal.id,
                pedido_id=mensagem.id,
                dono_id=dono,
                instrucao=mensagem.texto,
                raiz_id=uuid4(),
                status=StatusTarefa.PARADA,
                motivo=MotivoParada.ROTEAMENTO_ILEGIVEL,
            )
            tarefa.raiz_id = tarefa.id
            await self._armazem.gravar_tarefa(tarefa)
            mudancas.tarefas.append(tarefa)
            mudancas.mensagens.append(
                await self._atividade(
                    canal,
                    "O líder não conseguiu decidir quem responde. Use Reatribuir.",
                    tarefa_id=tarefa.id,
                )
            )
            return mudancas
        await self._aplicar_rota(
            canal, mensagem, conferida.rota, await self._armazem.tarefas(canal.id), mudancas
        )
        return mudancas

    # ---------- turnos (o worker chama) ----------

    async def proximas(self, canal_id: UUID) -> list[TarefaCanal]:
        """Tarefas que podem começar agora: até 2 rodando por canal e uma por agente."""
        canal = await self._armazem.canal(canal_id)
        if canal is None or canal.arquivado:
            return []
        tarefas = await self._armazem.tarefas(canal_id)
        rodando = [t for t in tarefas if t.status is StatusTarefa.RODANDO]
        vagas = MAX_TAREFAS_RODANDO_POR_CANAL - len(rodando)
        ocupados = {t.dono_id for t in rodando}
        escolhidas: list[TarefaCanal] = []
        for tarefa in tarefas:
            if vagas <= 0:
                break
            if tarefa.status is StatusTarefa.NA_FILA and tarefa.dono_id not in ocupados:
                escolhidas.append(tarefa)
                ocupados.add(tarefa.dono_id)
                vagas -= 1
        return escolhidas

    async def iniciar(self, tarefa_id: UUID) -> TarefaCanal:
        tarefa = await self._tarefa(tarefa_id)
        if tarefa.status is not StatusTarefa.NA_FILA:
            raise ErroCanal("Esta tarefa não está esperando para começar.")
        tarefa.status = StatusTarefa.RODANDO
        tarefa.atualizada_em = _agora()
        await self._armazem.gravar_tarefa(tarefa)
        return tarefa

    async def resposta_do_agente(
        self, tarefa_id: UUID, revisao: int, texto: str, anexos: Sequence[UUID] = ()
    ) -> MensagemCanal | None:
        """O que o agente escreveu no turno vira mensagem do canal (todos veem)."""
        tarefa = await self._tarefa(tarefa_id)
        if tarefa.revisao != revisao or tarefa.status is not StatusTarefa.RODANDO:
            return None  # turno velho: não aparece no canal
        canal = await self._canal(tarefa.canal_id)
        mensagem = MensagemCanal(
            id=uuid4(),
            canal_id=canal.id,
            seq=await self._armazem.proximo_seq(canal.id),
            autor=AutorCanal.AGENTE,
            agente_id=tarefa.dono_id,
            texto=texto.strip(),
            responde_a=tarefa.pedido_id,
            tarefa_id=tarefa.id,
            anexos=tuple(anexos),
        )
        await self._armazem.gravar_mensagem(mensagem)
        return mensagem

    async def fim_do_turno(self, tarefa_id: UUID, revisao: int) -> Mudancas:
        """O turno acabou sem ``canal_resultado``: espera as filhas ou dá a tarefa por feita."""
        tarefa = await self._tarefa(tarefa_id)
        mudancas = Mudancas()
        if tarefa.revisao != revisao or tarefa.status is not StatusTarefa.RODANDO:
            return mudancas
        if await self._tem_filhas_abertas(tarefa):
            tarefa.status = StatusTarefa.AGUARDANDO_FILHAS
        else:
            tarefa.status = StatusTarefa.CONCLUIDA
        tarefa.atualizada_em = _agora()
        await self._armazem.gravar_tarefa(tarefa)
        mudancas.tarefas.append(tarefa)
        if tarefa.status is StatusTarefa.CONCLUIDA:
            await self._acordar_pai(tarefa, mudancas)
        return mudancas

    async def falhar(self, tarefa_id: UUID, revisao: int, erro: str) -> Mudancas:
        tarefa = await self._tarefa(tarefa_id)
        mudancas = Mudancas()
        if tarefa.revisao != revisao or tarefa.status not in EM_ANDAMENTO:
            return mudancas
        tarefa.status = StatusTarefa.FALHOU
        tarefa.erro = erro[:500]
        tarefa.atualizada_em = _agora()
        await self._armazem.gravar_tarefa(tarefa)
        mudancas.tarefas.append(tarefa)
        return mudancas

    async def recuperar_apos_queda(self) -> list[TarefaCanal]:
        """Turno que estava rodando quando o servidor caiu vira "parada (interrompida)"."""
        afetadas = []
        for tarefa in await self._armazem.tarefas_abertas():
            if tarefa.status is StatusTarefa.RODANDO:
                self._parar(tarefa, MotivoParada.INTERROMPIDA)
                await self._armazem.gravar_tarefa(tarefa)
                afetadas.append(tarefa)
        return afetadas

    # ---------- ferramentas dos agentes ----------

    async def delegar(
        self,
        tarefa_id: UUID,
        revisao: int,
        *,
        por_agente: UUID,
        para_agente: UUID,
        instrucao: str,
        disponiveis: set[UUID],
    ) -> TarefaCanal:
        pai = await self._tarefa_do_dono(tarefa_id, revisao, por_agente)
        canal = await self._canal(pai.canal_id)
        instrucao = instrucao.strip()
        if not instrucao:
            raise ErroCanal("Diga o que o colega precisa fazer.")
        if para_agente == por_agente:
            raise ErroCanal("Você não pode delegar para si mesmo.")
        if para_agente not in canal.membros or para_agente not in disponiveis:
            raise ErroCanal("Só dá para delegar a membros deste canal que estão disponíveis.")
        if para_agente == pai.delegada_por:
            raise ErroCanal(
                "Não devolva a tarefa para quem te passou. Termine com o que tem e "
                "registre o resultado, ou diga o que bloqueia."
            )
        tarefas = await self._armazem.tarefas(canal.id)
        da_raiz = [t for t in tarefas if t.raiz_id == pai.raiz_id and not t.raiz]
        if len(da_raiz) >= MAX_DELEGACOES_POR_PEDIDO:
            raise ErroCanal(
                f"Este pedido já gerou {MAX_DELEGACOES_POR_PEDIDO} tarefas delegadas. "
                "Termine com o que tem."
            )
        filha = TarefaCanal(
            id=uuid4(),
            canal_id=canal.id,
            pedido_id=pai.pedido_id,
            dono_id=para_agente,
            instrucao=instrucao,
            raiz_id=pai.raiz_id,
            pai_id=pai.id,
            delegada_por=por_agente,
        )
        await self._armazem.gravar_tarefa(filha)
        await self._atividade(
            canal, f"Delegou: {instrucao[:120]}", agente_id=por_agente, tarefa_id=filha.id
        )
        return filha

    async def transferir(
        self,
        tarefa_id: UUID,
        revisao: int,
        *,
        por_agente: UUID,
        para_agente: UUID,
        nota: str,
        disponiveis: set[UUID],
    ) -> TarefaCanal:
        """Passa a tarefa inteira para outro membro. O turno de quem passou acaba aqui."""
        tarefa = await self._tarefa_do_dono(tarefa_id, revisao, por_agente)
        canal = await self._canal(tarefa.canal_id)
        if para_agente == por_agente:
            raise ErroCanal("A tarefa já é sua.")
        if para_agente not in canal.membros or para_agente not in disponiveis:
            raise ErroCanal("Só dá para transferir a membros deste canal que estão disponíveis.")
        tarefa.dono_id = para_agente
        tarefa.delegada_por = por_agente
        tarefa.revisao += 1
        tarefa.status = StatusTarefa.NA_FILA
        if nota.strip():
            tarefa.instrucao = f"{tarefa.instrucao}\n\nNota de quem passou: {nota.strip()}"
        tarefa.atualizada_em = _agora()
        await self._armazem.gravar_tarefa(tarefa)
        await self._atividade(
            canal, "Transferiu a tarefa.", agente_id=por_agente, tarefa_id=tarefa.id
        )
        return tarefa

    async def registrar_resultado(
        self, tarefa_id: UUID, revisao: int, *, por_agente: UUID, texto: str
    ) -> Mudancas:
        tarefa = await self._tarefa_do_dono(tarefa_id, revisao, por_agente)
        texto = texto.strip()
        if not texto:
            raise ErroCanal("O resultado está vazio.")
        if await self._tem_filhas_abertas(tarefa):
            raise ErroCanal(
                "Ainda há tarefas delegadas abertas. Espere os resultados delas ou peça ao "
                "usuário para cancelar."
            )
        canal = await self._canal(tarefa.canal_id)
        tarefa.resultado = texto[:MAX_TEXTO_MENSAGEM]
        tarefa.status = StatusTarefa.CONCLUIDA
        tarefa.atualizada_em = _agora()
        await self._armazem.gravar_tarefa(tarefa)
        mensagem = MensagemCanal(
            id=uuid4(),
            canal_id=canal.id,
            seq=await self._armazem.proximo_seq(canal.id),
            autor=AutorCanal.AGENTE,
            agente_id=por_agente,
            texto=tarefa.resultado,
            tipo=TipoMensagemCanal.RESULTADO,
            responde_a=tarefa.pedido_id,
            tarefa_id=tarefa.id,
        )
        await self._armazem.gravar_mensagem(mensagem)
        mudancas = Mudancas(mensagens=[mensagem], tarefas=[tarefa])
        await self._acordar_pai(tarefa, mudancas)
        return mudancas

    # ---------- controles do usuário ----------

    async def parar(self, tarefa_id: UUID, usuario_id: UUID) -> Mudancas:
        """Para a tarefa e tudo o que ela delegou."""
        tarefa = await self._tarefa(tarefa_id)
        canal = await self._do_usuario(tarefa.canal_id, usuario_id)
        mudancas = Mudancas()
        for alvo in [tarefa, *await self._descendentes(tarefa)]:
            if alvo.status in EM_ANDAMENTO:
                if alvo.status is StatusTarefa.RODANDO:
                    mudancas.interromper.append(alvo.id)
                self._parar(alvo, MotivoParada.PARADA_PELO_USUARIO)
                await self._armazem.gravar_tarefa(alvo)
                mudancas.tarefas.append(alvo)
        if mudancas.tarefas:
            mudancas.mensagens.append(
                await self._atividade(canal, "Você parou a tarefa.", tarefa_id=tarefa.id)
            )
        return mudancas

    async def retomar(
        self, tarefa_id: UUID, usuario_id: UUID, *, disponiveis: set[UUID]
    ) -> Mudancas:
        tarefa = await self._tarefa(tarefa_id)
        canal = await self._do_usuario(tarefa.canal_id, usuario_id)
        if canal.arquivado:
            raise ErroCanal("Restaure o canal antes de retomar.")
        if tarefa.status not in (StatusTarefa.PARADA, StatusTarefa.FALHOU):
            raise ErroCanal("Só dá para retomar uma tarefa parada ou que falhou.")
        if tarefa.dono_id not in canal.membros or tarefa.dono_id not in disponiveis:
            raise ErroCanal("O responsável não está disponível. Use Reatribuir.")
        reabertas = await self._reabrir_arvore(tarefa, canal)
        return Mudancas(tarefas=reabertas)

    async def reatribuir(
        self, tarefa_id: UUID, usuario_id: UUID, *, novo_dono: UUID, disponiveis: set[UUID]
    ) -> Mudancas:
        tarefa = await self._tarefa(tarefa_id)
        canal = await self._do_usuario(tarefa.canal_id, usuario_id)
        if canal.arquivado:
            raise ErroCanal("Restaure o canal antes de reatribuir.")
        if tarefa.status not in (StatusTarefa.PARADA, StatusTarefa.FALHOU):
            raise ErroCanal("Pare a tarefa antes de reatribuir.")
        if novo_dono not in canal.membros or novo_dono not in disponiveis:
            raise ErroCanal("Escolha um membro disponível deste canal.")
        tarefa.dono_id = novo_dono
        tarefa.delegada_por = None
        self._reabrir(tarefa, await self._tem_filhas_abertas(tarefa))
        await self._armazem.gravar_tarefa(tarefa)
        atividade = await self._atividade(
            canal, "Você reatribuiu a tarefa.", agente_id=novo_dono, tarefa_id=tarefa.id
        )
        return Mudancas(mensagens=[atividade], tarefas=[tarefa])

    async def cancelar(self, tarefa_id: UUID, usuario_id: UUID) -> Mudancas:
        """Encerra o pedido inteiro (a raiz e tudo o que ela delegou). As mensagens ficam."""
        tarefa = await self._tarefa(tarefa_id)
        canal = await self._do_usuario(tarefa.canal_id, usuario_id)
        if tarefa.status not in (StatusTarefa.PARADA, StatusTarefa.FALHOU):
            raise ErroCanal("Pare a tarefa antes de cancelar.")
        mudancas = Mudancas()
        for alvo in await self._armazem.tarefas(canal.id):
            if alvo.raiz_id == tarefa.raiz_id and alvo.status in ABERTAS | {StatusTarefa.FALHOU}:
                if alvo.status is StatusTarefa.RODANDO:
                    mudancas.interromper.append(alvo.id)
                alvo.status = StatusTarefa.CANCELADA
                alvo.atualizada_em = _agora()
                await self._armazem.gravar_tarefa(alvo)
                mudancas.tarefas.append(alvo)
        mudancas.mensagens.append(
            await self._atividade(canal, "Você cancelou o pedido.", tarefa_id=tarefa.raiz_id)
        )
        return mudancas

    # ---------- leitura ----------

    async def historico(
        self, canal_id: UUID, usuario_id: UUID, *, depois_de_seq: int = 0, limite: int = 50
    ) -> list[MensagemCanal]:
        await self._do_usuario(canal_id, usuario_id)
        limite = max(1, min(limite, 200))
        return [m for m in await self._armazem.mensagens(canal_id) if m.seq > depois_de_seq][
            :limite
        ]

    async def tarefas(self, canal_id: UUID) -> list[TarefaCanal]:
        return await self._armazem.tarefas(canal_id)

    async def canal(self, canal_id: UUID) -> Canal:
        return await self._canal(canal_id)

    # ---------- interno ----------

    def _parar(self, tarefa: TarefaCanal, motivo: MotivoParada | None) -> None:
        tarefa.status = StatusTarefa.PARADA
        tarefa.motivo = motivo
        tarefa.atualizada_em = _agora()

    def _reabrir(self, tarefa: TarefaCanal, tem_filhas: bool) -> None:
        tarefa.revisao += 1
        tarefa.motivo = None
        tarefa.erro = None
        tarefa.status = StatusTarefa.AGUARDANDO_FILHAS if tem_filhas else StatusTarefa.NA_FILA
        tarefa.atualizada_em = _agora()

    async def _reabrir_arvore(self, tarefa: TarefaCanal, canal: Canal) -> list[TarefaCanal]:
        """Reabre a tarefa e as descendentes que pararam junto (de baixo para cima)."""
        reabertas = []
        alvos = [tarefa, *await self._descendentes(tarefa)]
        for alvo in reversed(alvos):
            if alvo.status in (StatusTarefa.PARADA, StatusTarefa.FALHOU) and (
                alvo is tarefa or alvo.motivo is not MotivoParada.DONO_SAIU
            ):
                if alvo.dono_id not in canal.membros:
                    continue
                self._reabrir(alvo, await self._tem_filhas_abertas(alvo))
                await self._armazem.gravar_tarefa(alvo)
                reabertas.append(alvo)
        return reabertas

    async def _acordar_pai(self, tarefa: TarefaCanal, mudancas: Mudancas) -> None:
        if tarefa.pai_id is None:
            return
        pai = await self._tarefa(tarefa.pai_id)
        if pai.status is StatusTarefa.AGUARDANDO_FILHAS and not await self._tem_filhas_abertas(pai):
            pai.status = StatusTarefa.NA_FILA
            pai.atualizada_em = _agora()
            await self._armazem.gravar_tarefa(pai)
            mudancas.tarefas.append(pai)

    async def _filhas(self, tarefa: TarefaCanal) -> list[TarefaCanal]:
        return [t for t in await self._armazem.tarefas(tarefa.canal_id) if t.pai_id == tarefa.id]

    async def _descendentes(self, tarefa: TarefaCanal) -> list[TarefaCanal]:
        todas = await self._armazem.tarefas(tarefa.canal_id)
        resultado: list[TarefaCanal] = []
        fronteira = [tarefa.id]
        while fronteira:
            atual = fronteira.pop()
            filhas = [t for t in todas if t.pai_id == atual]
            resultado.extend(filhas)
            fronteira.extend(t.id for t in filhas)
        return resultado

    async def _tem_filhas_abertas(self, tarefa: TarefaCanal) -> bool:
        return any(t.status in ABERTAS for t in await self._filhas(tarefa))

    async def _tarefa(self, tarefa_id: UUID) -> TarefaCanal:
        tarefa = await self._armazem.tarefa(tarefa_id)
        if tarefa is None:
            raise ErroCanal("Tarefa não encontrada.")
        return tarefa

    async def _tarefa_do_dono(self, tarefa_id: UUID, revisao: int, agente_id: UUID) -> TarefaCanal:
        tarefa = await self._tarefa(tarefa_id)
        if tarefa.dono_id != agente_id:
            raise ErroCanal("Esta tarefa não é sua.")
        if tarefa.revisao != revisao or tarefa.status is not StatusTarefa.RODANDO:
            raise ErroCanal(
                "Esta tarefa mudou (foi parada, retomada ou passada a outro). Pare aqui."
            )
        return tarefa

    async def _canal(self, canal_id: UUID) -> Canal:
        canal = await self._armazem.canal(canal_id)
        if canal is None:
            raise ErroCanal("Canal não encontrado.")
        return canal

    async def _do_usuario(self, canal_id: UUID, usuario_id: UUID) -> Canal:
        canal = await self._armazem.canal(canal_id)
        # Mesmo erro para "não existe" e "não é seu".
        if canal is None or canal.usuario_id != usuario_id:
            raise ErroCanal("Canal não encontrado.")
        return canal

    async def _atividade(
        self,
        canal: Canal,
        texto: str,
        *,
        agente_id: UUID | None = None,
        tarefa_id: UUID | None = None,
    ) -> MensagemCanal:
        mensagem = MensagemCanal(
            id=uuid4(),
            canal_id=canal.id,
            seq=await self._armazem.proximo_seq(canal.id),
            autor=AutorCanal.SISTEMA,
            texto=texto,
            agente_id=agente_id,
            tipo=TipoMensagemCanal.ATIVIDADE,
            tarefa_id=tarefa_id,
        )
        await self._armazem.gravar_mensagem(mensagem)
        return mensagem

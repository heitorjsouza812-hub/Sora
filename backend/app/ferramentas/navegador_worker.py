"""Adaptador das ferramentas ``navegador_*`` para o runtime Playwright do worker."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select

from app.core.config import obter_configuracao
from app.eventos.equipe import AbaNavegadorEvento
from app.eventos.streams import publicar_evento
from app.eventos.tipos import AprovacaoPedida
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import StatusAprovacao
from app.modelos.tabelas import Anexo, Aprovacao, Conversa
from app.navegador.abas import (
    Aba,
    GerenteAbas,
    RevisaoNavegacaoNecessaria,
)
from app.navegador.arvore import ServicoArvore, para_modelo
from app.navegador.persistente import MotorPlaywright
from app.navegador.repositorio import RepositorioNavegador


@dataclass(slots=True)
class AmbienteNavegador:
    gerente: GerenteAbas
    motor: MotorPlaywright
    arvore: ServicoArvore
    repositorio: RepositorioNavegador
    sessoes: Any
    redis: Any

    async def _conversa(self, contexto: ContextoFerramenta) -> UUID | None:
        if contexto.conversa_id:
            return contexto.conversa_id
        async with self.sessoes() as sessao:
            return await sessao.scalar(
                select(Conversa.id)
                .where(
                    Conversa.usuario_id == contexto.usuario_id,
                    Conversa.agente_id == contexto.agente_id,
                )
                .order_by(Conversa.criada_em.desc())
            )

    async def publicar_aba(
        self,
        aba: Aba,
        contexto: ContextoFerramenta,
        *,
        fechada: bool = False,
        ajuda: str | None = None,
    ) -> None:
        conversa_id = await self._conversa(contexto)
        if conversa_id is None:
            return
        await publicar_evento(
            self.redis,
            AbaNavegadorEvento(
                aba_id=aba.id,
                agente_id=aba.agente_id,
                url=aba.url,
                titulo=aba.titulo,
                carregada=aba.carregada,
                assumida_pelo_usuario=aba.assumida_pelo_usuario,
                fechada=fechada,
                pedido_de_ajuda=ajuda,
            ),
            conversa_id,
            aba.usuario_id,
        )

    async def _sincronizar_assuncao(self, aba: Aba) -> Aba:
        assumida = bool(await self.redis.exists(f"navegador:assumida:{aba.id}"))
        if assumida != aba.assumida_pelo_usuario:
            aba = (
                self.gerente.assumir(aba.id, aba.usuario_id)
                if assumida
                else self.gerente.devolver(aba.id, aba.usuario_id)
            )
        await self.motor.recarregar_estado(aba)
        return aba

    def _aba(self, contexto: ContextoFerramenta, aba_id: UUID | None) -> Aba:
        abas = self.gerente.do_agente(contexto.agente_id, so_efemeras=contexto.sem_supervisao)
        if aba_id is not None:
            for aba in abas:
                if aba.id == aba_id:
                    return aba
            raise ErroFerramenta("Essa aba não existe ou não é sua.")
        if not abas:
            raise ErroFerramenta("Você não tem abas abertas. Use navegador_abrir.")
        return max(abas, key=lambda item: item.usada_em)

    async def _pedir_revisao(
        self,
        contexto: ContextoFerramenta,
        ferramenta: str,
        revisao: RevisaoNavegacaoNecessaria,
    ) -> str:
        if revisao.aba_id is None:
            raise ErroFerramenta(str(revisao))
        escopo = contexto.etapa_id or contexto.conversa_id
        aprovacao_id = uuid5(
            NAMESPACE_URL, f"sora:dominio:{escopo}:{revisao.particao}:{revisao.dominio}"
        )
        agora = datetime.now(UTC)
        expira_em = agora + timedelta(minutes=10)
        criada = False
        async with self.sessoes() as sessao:
            aprovacao = await sessao.get(Aprovacao, aprovacao_id, with_for_update=True)
            if aprovacao is not None and aprovacao.status == StatusAprovacao.NEGADA:
                return f"Erro: o usuário negou acesso ao domínio {revisao.dominio}."
            if aprovacao is None:
                aprovacao = Aprovacao(
                    id=aprovacao_id,
                    usuario_id=contexto.usuario_id,
                    etapa_id=contexto.etapa_id,
                    agente_id=contexto.agente_id,
                    acao={
                        "tipo": "aprovar_dominio",
                        "ferramenta": ferramenta,
                        "aba_id": str(revisao.aba_id),
                        "dominio": revisao.dominio,
                        "url": revisao.url,
                        "particao": revisao.particao,
                        "conversa_id": str(contexto.conversa_id),
                    },
                    avaliacao={
                        "resumo": f"Permitir acesso a {revisao.dominio}",
                        "dano": "O perfil desta aba tem login salvo.",
                    },
                    expira_em=expira_em,
                )
                sessao.add(aprovacao)
                criada = True
                await sessao.commit()
            else:
                expira_em = aprovacao.expira_em
        if criada:
            await publicar_evento(
                self.redis,
                AprovacaoPedida(
                    aprovacao_id=aprovacao_id,
                    resumo=f"Permitir acesso a {revisao.dominio}?",
                    dano=(
                        "O perfil desta aba tem login salvo; o novo domínio poderá receber cookies."
                    ),
                    quem_recebe=revisao.dominio,
                    expira_em=expira_em,
                    tipo="aprovar_dominio",
                    dominio=revisao.dominio,
                    url=revisao.url,
                    perfil={"particao": revisao.particao},
                    agente_id=contexto.agente_id,
                    opcoes=[
                        {"rotulo": "Aprovar domínio", "valor": "sempre_permitir"},
                        {"rotulo": "Negar", "valor": "negar"},
                    ],
                ),
                contexto.conversa_id,
                contexto.usuario_id,
            )
        from langgraph.types import interrupt

        if revisao.particao:
            # Ao retomar, a ferramenta roda de novo: o estado já aprovado vem do banco.
            await self.motor.recarregar_estado_da_particao(revisao.particao)
        decisao = interrupt(
            {"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id), "dominio": revisao.dominio}
        )
        if str(decisao) == "negar":
            return f"Erro: o usuário negou acesso ao domínio {revisao.dominio}."
        return "Domínio aprovado. Repita a navegação."

    async def executar(self, nome: str, args: Any, contexto: ContextoFerramenta) -> Any:
        try:
            if nome == "navegador_abrir":
                escolha = await self.repositorio.escolha_do_agente(
                    contexto.agente_id, contexto.usuario_id
                )
                aba = await self.gerente.abrir(
                    usuario_id=contexto.usuario_id,
                    agente_id=contexto.agente_id,
                    escolha=escolha,
                    url=args.url,
                    sem_supervisao=contexto.sem_supervisao,
                )
                await self.repositorio.salvar_aba(aba)
                await self.publicar_aba(aba, contexto)
                return {
                    "resumo": "Aba aberta.",
                    "aba_id": str(aba.id),
                    "url": aba.url,
                    "titulo": aba.titulo,
                }

            if nome == "navegador_abas":
                return {
                    "resumo": self.gerente.descrever(contexto.agente_id),
                    "abas": [self._estado(a) for a in self.gerente.do_agente(contexto.agente_id)],
                }

            aba = self._aba(contexto, getattr(args, "aba_id", None))
            aba = await self._sincronizar_assuncao(aba)
            if nome == "navegador_fechar_aba":
                await self.gerente.fechar(
                    aba.id, contexto.agente_id, sem_supervisao=contexto.sem_supervisao
                )
                await self.repositorio.remover_aba(aba.id)
                self.arvore.esquecer_aba(aba.id)
                await self.publicar_aba(aba, contexto, fechada=True)
                return {"resumo": "Aba fechada.", "aba_id": str(aba.id)}
            if nome == "navegador_console":
                linhas = self.gerente.console(
                    aba.id, contexto.agente_id, so_erros=args.so_erros, limite=args.limite
                )
                return {
                    "resumo": f"{len(linhas)} linhas de console.",
                    "itens": [
                        {
                            "nivel": linha.nivel,
                            "texto": linha.texto,
                            "momento": linha.momento.isoformat(),
                        }
                        for linha in linhas
                    ],
                }
            if nome == "navegador_capturar":
                dados = await self.gerente.capturar(aba.id, contexto.agente_id)
                return await self._salvar_captura(contexto.usuario_id, aba.id, dados)
            if nome == "navegador_pedir_ajuda":
                await self.publicar_aba(aba, contexto, ajuda=args.motivo)
                return {"resumo": "Pedi ao usuário para assumir a aba.", "aba_id": str(aba.id)}

            resposta = await self.arvore.executar(nome, args, contexto)
            if revisao := self.motor.consumir_revisao(aba):
                # o clique foi abortado e a aba ficou na página de erro: volta para onde estava
                with contextlib.suppress(Exception):
                    await self.motor.pagina(aba).goto(aba.url, wait_until="domcontentloaded")
                raise revisao
            pagina = self.motor.pagina(aba)
            aba = self.gerente.sincronizar_pagina(
                aba.id, url=pagina.url, titulo=await pagina.title()
            )
            await self.repositorio.salvar_aba(aba)
            await self.publicar_aba(aba, contexto)
            saida: dict[str, Any] = {
                "resumo": para_modelo(resposta),
                "url": aba.url,
                "titulo": aba.titulo,
            }
            if rastro := self.arvore.ultimo_rastro(aba.id):
                saida["rastro"] = rastro
            return saida
        except RevisaoNavegacaoNecessaria as revisao:
            if nome == "navegador_abrir" and revisao.aba_id is not None:
                # a aba nasceu só para esta navegação barrada; a repetição abre outra
                with contextlib.suppress(ErroFerramenta):
                    await self.gerente.fechar(
                        revisao.aba_id, contexto.agente_id, sem_supervisao=contexto.sem_supervisao
                    )
            return await self._pedir_revisao(contexto, nome, revisao)

    @staticmethod
    def _estado(aba: Aba) -> dict[str, Any]:
        return {
            "aba_id": str(aba.id),
            "agente_id": str(aba.agente_id),
            "url": aba.url,
            "titulo": aba.titulo,
            "carregada": aba.carregada,
            "assumida_pelo_usuario": aba.assumida_pelo_usuario,
        }

    async def _salvar_captura(self, usuario_id: UUID, aba_id: UUID, dados: bytes) -> dict[str, Any]:
        anexo_id = uuid4()
        nome = f"navegador-{aba_id}.png"
        relativo = f"{usuario_id}/{anexo_id}"
        destino = obter_configuracao().pasta_arquivos / relativo
        await asyncio.to_thread(destino.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(destino.write_bytes, dados)
        async with self.sessoes() as sessao:
            sessao.add(
                Anexo(
                    id=anexo_id,
                    usuario_id=usuario_id,
                    nome=nome,
                    tipo="image/png",
                    tamanho=len(dados),
                    caminho=relativo,
                    origem="navegador",
                )
            )
            await sessao.commit()
        return {
            "resumo": "Captura da aba pronta.",
            "anexo_id": str(anexo_id),
            "nome": nome,
            "tipo": "image/png",
            "tamanho": len(dados),
            "url": f"/v1/anexos/{anexo_id}",
        }


_ambiente: AmbienteNavegador | None = None


def configurar(ambiente: AmbienteNavegador | None) -> None:
    global _ambiente
    _ambiente = ambiente


async def executar(nome: str, args: Any, contexto: ContextoFerramenta) -> Any:
    if _ambiente is None:
        raise ErroFerramenta("O navegador não foi iniciado neste worker.")
    return await _ambiente.executar(nome, args, contexto)


def _adaptador(nome: str):
    async def ferramenta(args: Any, contexto: ContextoFerramenta) -> Any:
        return await executar(nome, args, contexto)

    ferramenta.__name__ = nome
    return ferramenta


for _nome in (
    "navegador_abrir",
    "navegador_abas",
    "navegador_fechar_aba",
    "navegador_capturar",
    "navegador_console",
    "navegador_pedir_ajuda",
    "navegador_observar",
    "navegador_procurar",
    "navegador_elemento",
    "navegador_esperar",
    "navegador_acao",
    "navegador_tecla",
    "navegador_lote",
):
    globals()[_nome] = _adaptador(_nome)

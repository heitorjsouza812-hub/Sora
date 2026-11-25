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
from app.modelos.tabelas import Anexo, Aprovacao, Conversa, PerfilNavegador
from app.navegador.abas import (
    Aba,
    GerenteAbas,
    RevisaoNavegacaoNecessaria,
)
from app.navegador.arvore import ServicoArvore, para_modelo
from app.navegador.perfis import (
    EscolhaPerfil,
    TipoPerfil,
    dominios_aprovados,
    ler_particao,
)
from app.navegador.persistente import MotorPlaywright
from app.navegador.repositorio import RepositorioNavegador

MAX_CARTOES_POR_DOMINIO = 5


@dataclass(slots=True)
class AmbienteNavegador:
    gerente: GerenteAbas
    motor: MotorPlaywright
    arvore: ServicoArvore
    repositorio: RepositorioNavegador
    sessoes: Any
    redis: Any
    abrindo: int = 0
    """Abas sendo abertas agora (ainda não gravadas): a conferência com o banco espera."""

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
            raise ErroFerramenta(
                "Essa aba não existe mais (foi fechada, ou era temporária e vive em outro "
                "servidor). Veja suas abas com navegador_abas ou abra uma nova."
            )
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
        base = f"sora:dominio:{escopo}:{revisao.particao}:{revisao.dominio}"
        agora = datetime.now(UTC)
        expira_em = agora + timedelta(minutes=10)
        criada = False
        aprovados_hoje = dominios_aprovados(
            await self.repositorio.ler_estado(revisao.particao) if revisao.particao else None
        )
        async with self.sessoes() as sessao:
            # Mesma etapa, mesmo domínio: o cartão é um só enquanto vale. Cartão já usado e
            # domínio de novo barrado (revogado depois) ou cartão expirado pedem um cartão novo.
            for tentativa in range(MAX_CARTOES_POR_DOMINIO):
                chave = base if tentativa == 0 else f"{base}:{tentativa}"
                aprovacao_id = uuid5(NAMESPACE_URL, chave)
                aprovacao = await sessao.get(Aprovacao, aprovacao_id, with_for_update=True)
                if aprovacao is None:
                    aprovacao = Aprovacao(
                        id=aprovacao_id,
                        usuario_id=contexto.usuario_id,
                        etapa_id=contexto.etapa_id,
                        agente_id=contexto.agente_id,
                        grupo_id=contexto.canal_id,
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
                    break
                if aprovacao.status == StatusAprovacao.NEGADA:
                    return f"Erro: o usuário negou acesso ao domínio {revisao.dominio}."
                if aprovacao.status == StatusAprovacao.PENDENTE:
                    expira_em = aprovacao.expira_em
                    break
                if (
                    aprovacao.status == StatusAprovacao.PERMITIDA
                    and revisao.dominio.lower() in aprovados_hoje
                ):
                    break  # a ferramenta rodou de novo depois da decisão: o interrupt devolve
                # EXPIRADA, ou PERMITIDA mas revogada depois: tenta o próximo número
            else:
                return "Erro: pedidos de acesso demais para este domínio. Tente mais tarde."
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
                    perfil=await self._perfil_do_cartao(revisao.particao),
                    agente_id=contexto.agente_id,
                    conversa_id=contexto.conversa_id,
                    bot_id=contexto.agente_id,
                    grupo_id=contexto.canal_id,
                    opcoes=[
                        {"rotulo": "Aprovar domínio", "valor": "permitir_uma_vez"},
                        {"rotulo": "Negar", "valor": "negar"},
                    ],
                ),
                contexto.conversa_id,
                contexto.usuario_id,
            )
            from app.atencao import publicar_estado_atencao_persistido

            await publicar_estado_atencao_persistido(
                contexto.usuario_id, agente_id=contexto.agente_id, grupo_id=contexto.canal_id
            )
        from langgraph.types import interrupt

        if revisao.particao:
            # Ao retomar, a ferramenta roda de novo: o estado já aprovado vem do banco.
            await self.motor.recarregar_estado_da_particao(revisao.particao)
        decisao = interrupt(
            {"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id), "dominio": revisao.dominio}
        )
        if str(decisao) in ("negar", "negada"):
            return f"Erro: o usuário negou acesso ao domínio {revisao.dominio}."
        if str(decisao) == "expirada":
            return f"Erro: o pedido de acesso a {revisao.dominio} expirou sem resposta."
        return "Domínio aprovado. Repita a navegação."

    async def _pedir_senha(self, aba: Aba, args: Any, contexto: ContextoFerramenta) -> Any:
        """Senha segura (Onda 2): cartão no app, o usuário digita lá, a senha vai cifrada para o
        Redis por poucos minutos (``app/api/navegador_senha.py``) e é preenchida aqui, direto
        no campo. Nunca volta para o modelo nem entra no histórico do turno: o valor de retomada
        do turno é só a decisão (``permitir``/``negar``).

        Ao retomar, a ferramenta roda de novo do começo: o cartão é achado pelo mesmo id e o
        ``interrupt`` devolve a decisão."""
        from langgraph.types import interrupt

        from app.navegador.senha_segura import (
            MAX_CARTOES,
            VALIDADE_CARTAO,
            dominio_de,
            ler_e_apagar,
        )

        if contexto.sem_supervisao:
            raise ErroFerramenta(
                "Rotina roda sem ninguém olhando: não dá para pedir senha. Diga ao usuário que o "
                "site pede login e siga sem entrar."
            )
        navegador = await self.arvore.navegador_da_aba(contexto, aba.id)
        leitura = await navegador.elemento(args.ref, "valor")
        if not leitura.ok or not leitura.dados.get("senha"):
            raise ErroFerramenta(
                "Esse campo não é de senha. Use navegador_observar e passe a ref do campo de senha."
            )
        dominio = dominio_de(aba.url)
        escopo = contexto.etapa_id or contexto.conversa_id
        base = f"sora:senha:{escopo}:{aba.id}:{args.ref}"
        criada = False
        async with self.sessoes() as sessao:
            for tentativa in range(MAX_CARTOES):
                aprovacao_id = uuid5(
                    NAMESPACE_URL, base if tentativa == 0 else f"{base}:{tentativa}"
                )
                aprovacao = await sessao.get(Aprovacao, aprovacao_id, with_for_update=True)
                if aprovacao is None:
                    aprovacao = Aprovacao(
                        id=aprovacao_id,
                        usuario_id=contexto.usuario_id,
                        etapa_id=contexto.etapa_id,
                        agente_id=contexto.agente_id,
                        grupo_id=contexto.canal_id,
                        acao={
                            "tipo": "preencher_senha",
                            "ferramenta": "navegador_pedir_senha",
                            "aba_id": str(aba.id),
                            "ref": args.ref,
                            "dominio": dominio,
                            "motivo": args.motivo,
                            "conversa_id": str(contexto.conversa_id),
                        },
                        avaliacao={"resumo": f"Senha de {dominio}", "dano": "Login no site."},
                        expira_em=datetime.now(UTC) + VALIDADE_CARTAO,
                    )
                    sessao.add(aprovacao)
                    criada = True
                    await sessao.commit()
                    break
                consumida = bool((aprovacao.acao or {}).get("consumida"))
                if aprovacao.status == StatusAprovacao.PENDENTE:
                    if aprovacao.expira_em > datetime.now(UTC):
                        break  # esperando o usuário
                elif aprovacao.status != StatusAprovacao.EXPIRADA and not consumida:
                    break  # a ferramenta rodou de novo depois da decisão: o interrupt devolve
                # cartão já usado (senha errada, login de novo) ou vencido: tenta o próximo
            else:
                return (
                    "Erro: pedidos de senha demais para este campo. Peça ao usuário para "
                    "assumir a aba."
                )
        if criada:
            await publicar_evento(
                self.redis,
                AprovacaoPedida(
                    aprovacao_id=aprovacao_id,
                    resumo=f"Senha de {dominio}",
                    dano="O bot não vê a senha: ela vai direto para o campo da página.",
                    quem_recebe=dominio,
                    expira_em=aprovacao.expira_em,
                    tipo="preencher_senha",
                    dominio=dominio,
                    url=aba.url,
                    agente_id=contexto.agente_id,
                    conversa_id=contexto.conversa_id,
                    bot_id=contexto.agente_id,
                    grupo_id=contexto.canal_id,
                    opcoes=[
                        {"rotulo": "Preencher", "valor": "preencher_senha"},
                        {"rotulo": "Eu mesmo faço", "valor": "negar"},
                    ],
                ),
                contexto.conversa_id,
                contexto.usuario_id,
            )
            from app.atencao import publicar_estado_atencao_persistido

            await publicar_estado_atencao_persistido(
                contexto.usuario_id, agente_id=contexto.agente_id, grupo_id=contexto.canal_id
            )
        decisao = str(interrupt({"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id)}))
        senha = await ler_e_apagar(self.redis, contexto.usuario_id, aprovacao_id)
        async with self.sessoes() as sessao:
            linha = await sessao.get(Aprovacao, aprovacao_id, with_for_update=True)
            if linha is not None:
                linha.acao = {**linha.acao, "consumida": True}
                await sessao.commit()
        if decisao in ("negar", "negada"):
            return (
                "O usuário preferiu não digitar a senha aqui. Peça para ele assumir a aba "
                "(navegador_pedir_ajuda) ou siga sem entrar."
            )
        if decisao == "expirada" or senha is None:
            return "Erro: a senha não chegou a tempo. Peça de novo se ainda precisar entrar."
        aba_agora = self._aba(contexto, aba.id)
        if dominio_de(aba_agora.url) != dominio:
            del senha
            return (
                "Erro: a página mudou de site antes de preencher. Nada foi preenchido; abra de "
                "novo a página de login e peça a senha outra vez."
            )
        try:
            resposta = await navegador.agir(args.ref, "definir_valor", texto=senha)
        finally:
            del senha
        if not resposta.ok:
            return f"Erro: não consegui preencher o campo de senha. {para_modelo(resposta)}"
        return {
            "resumo": (
                "O usuário digitou a senha e ela foi preenchida no campo (você não vê o valor). "
                "Agora clique no botão de entrar."
            ),
            "aba_id": str(aba.id),
        }

    async def _perfil_do_cartao(self, nome_particao: str | None) -> dict[str, Any]:
        """``{tipo, perfil_id?, nome?}`` para o cartão; a partição (interna) nunca vai ao app."""
        lida = ler_particao(nome_particao or "")
        if lida is None:
            return {"tipo": "compartilhado"}
        if lida.tipo is TipoPerfil.NOMEADO and lida.perfil_id is not None:
            async with self.sessoes() as sessao:
                nome = await sessao.scalar(
                    select(PerfilNavegador.nome).where(PerfilNavegador.id == lida.perfil_id)
                )
            return {"tipo": "perfil", "perfil_id": str(lida.perfil_id), "nome": nome or "Perfil"}
        return {"tipo": lida.tipo.value}

    async def soltar_abas_fechadas(self, agente_id: UUID | None = None) -> None:
        """Remove da memória (e fecha a página) as abas salvas que já não existem no banco."""
        agentes = {agente_id} if agente_id else {a.agente_id for a in self.gerente.para_salvar()}
        for agente in agentes:
            salvas, perfis = await self.repositorio.carregar_abas_do_agente(agente)
            await self.gerente.sincronizar_com_banco(agente, salvas, perfis_por_usuario=perfis)

    async def _sincronizar_abas(self, contexto: ContextoFerramenta) -> None:
        """Mais de um worker: a aba pode ter nascido em outro. O banco manda: aba salva que este
        worker não conhece volta (descarregada, recarrega ao usar) e aba que sumiu do banco
        (fechada em outro worker ou pelo usuário) sai da memória. Aba efêmera não é salva."""
        if contexto.sem_supervisao:
            return
        salvas, perfis = await self.repositorio.carregar_abas_do_agente(contexto.agente_id)
        await self.gerente.sincronizar_com_banco(
            contexto.agente_id, salvas, perfis_por_usuario=perfis
        )

    async def _abrir(self, args: Any, contexto: ContextoFerramenta) -> Any:
        escolha = await self.repositorio.escolha_do_agente(contexto.agente_id, contexto.usuario_id)
        aba = await self.gerente.abrir(
            usuario_id=contexto.usuario_id,
            agente_id=contexto.agente_id,
            escolha=escolha or EscolhaPerfil(),
            url=args.url,
            # rotina, ou agente configurado como efêmero: aba descartável sem login
            sem_supervisao=contexto.sem_supervisao or escolha is None,
        )
        await self.repositorio.salvar_aba(aba)
        await self.publicar_aba(aba, contexto)
        return {
            "resumo": "Aba aberta.",
            "aba_id": str(aba.id),
            "url": aba.url,
            "titulo": aba.titulo,
        }

    async def executar(self, nome: str, args: Any, contexto: ContextoFerramenta) -> Any:
        try:
            await self._sincronizar_abas(contexto)
            if nome == "navegador_abrir":
                self.abrindo += 1
                try:
                    return await self._abrir(args, contexto)
                finally:
                    self.abrindo -= 1

            if nome == "navegador_abas":
                return {
                    "resumo": self.gerente.descrever(
                        contexto.agente_id, so_efemeras=contexto.sem_supervisao
                    ),
                    "abas": [
                        self._estado(a)
                        for a in self.gerente.do_agente(
                            contexto.agente_id, so_efemeras=contexto.sem_supervisao
                        )
                    ],
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
            if nome == "navegador_pedir_senha":
                return await self._pedir_senha(aba, args, contexto)

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
                "resumo": para_modelo(resposta, pedido=args),
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
    "navegador_pedir_senha",
    "navegador_observar",
    "navegador_procurar",
    "navegador_elemento",
    "navegador_esperar",
    "navegador_acao",
    "navegador_tecla",
    "navegador_lote",
):
    globals()[_nome] = _adaptador(_nome)

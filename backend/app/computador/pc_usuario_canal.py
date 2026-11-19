"""Canal entre o worker e o app de desktop para o alvo ``pc_usuario`` (C3).

O servidor **nunca** executa nada no PC: ele só põe comandos numa fila e espera a resposta. Quem
executa é a ponte do app de desktop (Tauri, ``app/src-tauri/src/pc/``), que busca os comandos
por long-poll autenticado (``GET /v1/computador-pc/comandos``) e devolve o resultado por POST.
Tudo passa pelo Redis compartilhado entre API e worker:

- ``pc:sessao:{usuario}``: a sessão do app de desktop conectado (uma por conta; a mais nova
  substitui a anterior), com os bots que o usuário ligou nele. Vence se o app parar de buscar.
- ``pc:fila:{sessao}``: comandos esperando o app. Cada comando tem id, prazo e uso único
  (``pc:cmd:{id}``, ``pc:entregue:{id}``, ``pc:usado:{id}``).
- ``pc:resp:{id}``: onde a API põe a resposta que o worker espera.
- ``pc:vez:{usuario}``: **um bot por vez** no PC; os outros recebem "o PC está em uso por X".
- ``pc:pausado:…``, ``pc:parado:…``, ``pc:uma_vez:…``: pausa por entrada física, Parar do usuário
  e programas liberados com "Permitir uma vez".
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.ferramentas.base import ErroFerramenta

CHAVE_SESSAO = "pc:sessao:{usuario_id}"
CHAVE_FILA = "pc:fila:{sessao_id}"
CHAVE_COMANDO = "pc:cmd:{comando_id}"
CHAVE_ENTREGUE = "pc:entregue:{comando_id}"
CHAVE_USADO = "pc:usado:{comando_id}"
CHAVE_RESPOSTA = "pc:resp:{comando_id}"
CHAVE_VEZ = "pc:vez:{usuario_id}"
CHAVE_PAUSADO = "pc:pausado:{usuario_id}:{agente_id}"
CHAVE_PARADO = "pc:parado:{usuario_id}:{agente_id}"
CHAVE_UMA_VEZ = "pc:uma_vez:v2:{usuario_id}:{agente_id}"
CHAVE_CARTAO = "pc:cartao:{usuario_id}:{agente_id}:{assunto}"

VALIDADE_SESSAO_S = 60
"""O app busca comandos a cada ≤ 25 s; sem buscar por 1 minuto, a sessão some."""
VEZ_S = 90
"""Quanto tempo o bot segura a vez sem mandar comando (o modelo pensa entre uma ação e outra)."""
UMA_VEZ_S = 5 * 60
""""Permitir uma vez" vence 5 min depois da decisão, com prazo absoluto por programa: usar não
renova (Cerca B2). Parar também apaga. Depois disso, a próxima ação no programa abre outro
cartão."""
PARADO_S = 120
"""Depois do Parar, o mesmo bot fica 2 min sem conseguir pegar o PC de novo."""
BLOQUEIO_S = 15 * 60
"""Um programa bloqueado abriu durante a ação do bot: ele fica parado até o usuário decidir o
cartão (ou por 15 min)."""
PAUSADO_S = 15 * 60
MAX_ESPERA_LONG_POLL_S = 25
MAX_AUTORIZADOS = 50
MAX_FILA = 20


class SemApp(ErroFerramenta):
    """Não há app de desktop conectado (ou o bot não está ligado nele)."""


@dataclass(frozen=True, slots=True)
class AgentePc:
    id: UUID
    nome: str
    cor: str

    def json(self) -> dict[str, str]:
        return {"id": str(self.id), "nome": self.nome, "cor": self.cor}


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    return valor.decode() if isinstance(valor, bytes) else str(valor)


@dataclass(slots=True)
class CanalPc:
    redis: Any

    # ---------- sessão do app de desktop ----------

    async def registrar_sessao(
        self,
        usuario_id: UUID,
        autorizados: list[UUID],
        dispositivo: str,
        *,
        login_sessao_id: UUID | None = None,
    ) -> str:
        """Nova sessão (substitui a anterior da mesma conta: só um PC por vez).

        ``login_sessao_id`` é a sessão de login do app de desktop que provou ser ela (token de
        renovação do cofre do Windows, Cerca B3): se ela acabar (sair, revogada), o PC solta."""
        anterior = await self.sessao(usuario_id)
        sessao_id = uuid4().hex
        dados = {
            "sessao_id": sessao_id,
            "autorizados": [str(a) for a in dict.fromkeys(autorizados)][:MAX_AUTORIZADOS],
            "dispositivo": dispositivo[:80],
            "desde": time.time(),
            "login_sessao_id": str(login_sessao_id) if login_sessao_id else None,
        }
        await self.redis.set(
            CHAVE_SESSAO.format(usuario_id=usuario_id), json.dumps(dados), ex=VALIDADE_SESSAO_S
        )
        if anterior:
            await self.redis.delete(CHAVE_FILA.format(sessao_id=anterior["sessao_id"]))
        return sessao_id

    async def sessao(self, usuario_id: UUID) -> dict[str, Any] | None:
        bruto = _texto(await self.redis.get(CHAVE_SESSAO.format(usuario_id=usuario_id)))
        if not bruto:
            return None
        try:
            dados = json.loads(bruto)
        except ValueError:
            return None
        return dados if isinstance(dados, dict) and dados.get("sessao_id") else None

    async def sessao_atual(self, usuario_id: UUID, sessao_id: str) -> dict[str, Any] | None:
        dados = await self.sessao(usuario_id)
        return dados if dados and dados["sessao_id"] == sessao_id else None

    async def tocar(self, usuario_id: UUID, sessao_id: str) -> bool:
        """Renova a validade da sessão (o app está vivo). False se ela não é mais a atual."""
        if await self.sessao_atual(usuario_id, sessao_id) is None:
            return False
        await self.redis.expire(CHAVE_SESSAO.format(usuario_id=usuario_id), VALIDADE_SESSAO_S)
        return True

    async def atualizar_autorizados(
        self, usuario_id: UUID, sessao_id: str, autorizados: list[UUID]
    ) -> bool:
        dados = await self.sessao_atual(usuario_id, sessao_id)
        if dados is None:
            return False
        dados["autorizados"] = [str(a) for a in dict.fromkeys(autorizados)][:MAX_AUTORIZADOS]
        await self.redis.set(
            CHAVE_SESSAO.format(usuario_id=usuario_id), json.dumps(dados), ex=VALIDADE_SESSAO_S
        )
        return True

    async def encerrar_da_sessao_de_login(self, usuario_id: UUID, login_sessao_id: UUID) -> bool:
        """Solta o PC preso a esta sessão de login (o usuário saiu no app de desktop).

        Antes o PC só soltava na próxima consulta do desktop (``/comandos`` respondia 409); com o
        token de acesso revogado ao sair, essa consulta para no 401 e não chega lá."""
        dados = await self.sessao(usuario_id)
        if not dados or dados.get("login_sessao_id") != str(login_sessao_id):
            return False
        if await self.encerrar_sessao(usuario_id, dados["sessao_id"]):
            await self.soltar_vez(usuario_id)
            return True
        return False

    async def encerrar_sessao(self, usuario_id: UUID, sessao_id: str) -> bool:
        if await self.sessao_atual(usuario_id, sessao_id) is None:
            return False
        await self.redis.delete(
            CHAVE_SESSAO.format(usuario_id=usuario_id), CHAVE_FILA.format(sessao_id=sessao_id)
        )
        return True

    # ---------- comandos (lado do app) ----------

    async def proximo_comando(
        self, usuario_id: UUID, sessao_id: str, espera_s: float
    ) -> dict[str, Any] | None:
        """Long-poll: o próximo comando ainda no prazo, entregue uma única vez."""
        fila = CHAVE_FILA.format(sessao_id=sessao_id)
        limite = time.monotonic() + max(0.0, min(espera_s, MAX_ESPERA_LONG_POLL_S))
        while True:
            restante = limite - time.monotonic()
            if restante <= 0:
                item = await self.redis.lpop(fila)
            else:
                par = await self.redis.blpop([fila], timeout=max(0.1, restante))
                item = par[1] if par else None
            comando_id = _texto(item)
            if comando_id is None:
                return None
            comando = await self._comando(comando_id)
            if (
                comando is None
                or comando["usuario_id"] != str(usuario_id)
                or comando["sessao_id"] != sessao_id
                or comando["prazo"] <= time.time()
            ):
                continue  # vencido ou de outra sessão: o worker já desistiu
            if not await self.redis.set(
                CHAVE_ENTREGUE.format(comando_id=comando_id), "1", nx=True, ex=600
            ):
                continue
            return comando["publico"]

    async def responder(
        self, usuario_id: UUID, sessao_id: str, comando_id: str, resposta: dict[str, Any]
    ) -> str:
        """``ok`` · ``nao_encontrado`` (outro dono/sessão ou id ruim) · ``usado`` · ``vencido``."""
        comando = await self._comando(comando_id)
        if (
            comando is None
            or comando["usuario_id"] != str(usuario_id)
            or comando["sessao_id"] != sessao_id
        ):
            return "nao_encontrado"
        if comando["prazo"] <= time.time():
            return "vencido"
        if not await self.redis.set(
            CHAVE_USADO.format(comando_id=comando_id), "1", nx=True, ex=600
        ):
            return "usado"
        chave = CHAVE_RESPOSTA.format(comando_id=comando_id)
        await self.redis.rpush(chave, json.dumps(resposta))
        await self.redis.expire(chave, 120)
        return "ok"

    async def _comando(self, comando_id: str) -> dict[str, Any] | None:
        if not comando_id or len(comando_id) > 64:
            return None
        bruto = _texto(await self.redis.get(CHAVE_COMANDO.format(comando_id=comando_id)))
        if not bruto:
            return None
        try:
            dados = json.loads(bruto)
        except ValueError:
            return None
        return dados if isinstance(dados, dict) else None

    # ---------- comandos (lado do worker) ----------

    async def enviar(
        self,
        usuario_id: UUID,
        sessao_id: str,
        agente: AgentePc,
        operacao: str,
        dados: dict[str, Any] | None,
        prazo_s: float,
        *,
        esperar: bool = True,
    ) -> dict[str, Any] | None:
        """Põe o comando na fila do app e espera a resposta até o prazo."""
        comando_id = uuid4().hex
        prazo = time.time() + prazo_s
        publico = {
            "id": comando_id,
            "agente": agente.json(),
            "operacao": operacao,
            "dados": dados or {},
            "prazo_ms": int(prazo_s * 1000),
            "prazo_em_ms": int(prazo * 1000),
        }
        registro = {
            "usuario_id": str(usuario_id),
            "sessao_id": sessao_id,
            "agente_id": str(agente.id),
            "prazo": prazo,
            "publico": publico,
        }
        fila = CHAVE_FILA.format(sessao_id=sessao_id)
        await self.redis.set(
            CHAVE_COMANDO.format(comando_id=comando_id),
            json.dumps(registro),
            ex=int(prazo_s) + 60,
        )
        await self.redis.rpush(fila, comando_id)
        await self.redis.ltrim(fila, -MAX_FILA, -1)
        await self.redis.expire(fila, int(prazo_s) + 60)
        if not esperar:
            return None
        par = await self.redis.blpop(
            [CHAVE_RESPOSTA.format(comando_id=comando_id)], timeout=max(0.1, prazo_s)
        )
        if not par:
            # o app não respondeu: o comando não vale mais (uso único) e o worker desiste
            await self.redis.set(CHAVE_USADO.format(comando_id=comando_id), "1", ex=600)
            raise ErroFerramenta(
                "O app de desktop não respondeu a tempo. Confira se a Sora está aberta no "
                "computador e tente de novo."
            )
        try:
            resposta = json.loads(_texto(par[1]) or "")
        except ValueError as erro:
            raise ErroFerramenta("O app de desktop mandou uma resposta inválida.") from erro
        if not isinstance(resposta, dict):
            raise ErroFerramenta("O app de desktop mandou uma resposta inválida.")
        return resposta

    # ---------- vez (um bot por vez) ----------

    async def quem_tem_a_vez(self, usuario_id: UUID) -> dict[str, Any] | None:
        bruto = _texto(await self.redis.get(CHAVE_VEZ.format(usuario_id=usuario_id)))
        if not bruto:
            return None
        try:
            dados = json.loads(bruto)
        except ValueError:
            return None
        return dados if isinstance(dados, dict) else None

    async def pegar_vez(self, usuario_id: UUID, agente: AgentePc) -> None:
        chave = CHAVE_VEZ.format(usuario_id=usuario_id)
        valor = json.dumps({"agente_id": str(agente.id), "nome": agente.nome})
        if await self.redis.set(chave, valor, nx=True, ex=VEZ_S):
            return
        dono = await self.quem_tem_a_vez(usuario_id)
        if dono is None:  # venceu entre o SET e o GET
            if await self.redis.set(chave, valor, nx=True, ex=VEZ_S):
                return
            dono = await self.quem_tem_a_vez(usuario_id) or {}
        if dono.get("agente_id") == str(agente.id):
            await self.redis.expire(chave, VEZ_S)
            return
        nome = str(dono.get("nome") or "outro bot")[:60]
        raise ErroFerramenta(
            f"O PC está em uso por {nome}. Só um bot usa o computador do usuário por vez: "
            "tente de novo quando ele terminar, ou siga sem o PC."
        )

    async def soltar_vez(self, usuario_id: UUID, agente_id: UUID | None = None) -> bool:
        """Devolve a vez. Com ``agente_id``, só se for dele."""
        chave = CHAVE_VEZ.format(usuario_id=usuario_id)
        if agente_id is not None:
            dono = await self.quem_tem_a_vez(usuario_id)
            if not dono or dono.get("agente_id") != str(agente_id):
                return False
        return bool(await self.redis.delete(chave))

    # ---------- pausa, Parar e "permitir uma vez" ----------

    async def marcar_pausado(self, usuario_id: UUID, agente_id: UUID) -> None:
        await self.redis.set(
            CHAVE_PAUSADO.format(usuario_id=usuario_id, agente_id=agente_id), "1", ex=PAUSADO_S
        )

    async def esta_pausado(self, usuario_id: UUID, agente_id: UUID) -> bool:
        return bool(
            await self.redis.exists(
                CHAVE_PAUSADO.format(usuario_id=usuario_id, agente_id=agente_id)
            )
        )

    async def limpar_pausa(self, usuario_id: UUID, agente_id: UUID) -> None:
        await self.redis.delete(CHAVE_PAUSADO.format(usuario_id=usuario_id, agente_id=agente_id))

    async def marcar_parado(self, usuario_id: UUID, agente_id: UUID) -> None:
        """Parar: tira a vez, a pausa e o "permitir uma vez" deste bot."""
        await self.redis.set(
            CHAVE_PARADO.format(usuario_id=usuario_id, agente_id=agente_id), "1", ex=PARADO_S
        )
        await self.redis.delete(
            CHAVE_PAUSADO.format(usuario_id=usuario_id, agente_id=agente_id),
            CHAVE_UMA_VEZ.format(usuario_id=usuario_id, agente_id=agente_id),
        )
        await self.soltar_vez(usuario_id, agente_id)

    async def esta_parado(self, usuario_id: UUID, agente_id: UUID) -> bool:
        return bool(
            await self.redis.exists(CHAVE_PARADO.format(usuario_id=usuario_id, agente_id=agente_id))
        )

    async def marcar_bloqueio(self, usuario_id: UUID, agente_id: UUID) -> None:
        """Programa bloqueado abriu na ação do bot: Parar mais longo, até o cartão ser decidido."""
        await self.marcar_parado(usuario_id, agente_id)
        await self.redis.set(
            CHAVE_PARADO.format(usuario_id=usuario_id, agente_id=agente_id), "1", ex=BLOQUEIO_S
        )

    async def limpar_parado(self, usuario_id: UUID, agente_id: UUID) -> None:
        await self.redis.delete(CHAVE_PARADO.format(usuario_id=usuario_id, agente_id=agente_id))

    async def bot_no_controle(self, usuario_id: UUID) -> bool:
        """Um bot desta conta está com a vez no PC e não está pausado (pode mexer agora)."""
        dono = await self.quem_tem_a_vez(usuario_id)
        if not dono:
            return False
        try:
            agente_id = UUID(str(dono.get("agente_id")))
        except ValueError:
            return True  # vez ilegível: na dúvida, há alguém no controle
        return not await self.esta_pausado(usuario_id, agente_id)

    async def permitir_uma_vez(self, usuario_id: UUID, agente_id: UUID, programa: str) -> None:
        """Libera ``programa`` até ``agora + UMA_VEZ_S``. Cada programa tem o próprio prazo."""
        chave = CHAVE_UMA_VEZ.format(usuario_id=usuario_id, agente_id=agente_id)
        await self.redis.hset(chave, programa, str(time.time() + UMA_VEZ_S))
        await self.redis.expire(chave, UMA_VEZ_S)

    async def programas_uma_vez(self, usuario_id: UUID, agente_id: UUID) -> set[str]:
        """Programas ainda no prazo. Ler não renova nada (Cerca B2)."""
        chave = CHAVE_UMA_VEZ.format(usuario_id=usuario_id, agente_id=agente_id)
        agora = time.time()
        programas: set[str] = set()
        for nome, prazo in (await self.redis.hgetall(chave)).items():
            try:
                vence = float(_texto(prazo) or 0)
            except ValueError:
                continue
            programa = _texto(nome)
            if programa and vence > agora:
                programas.add(programa)
        return programas

    # ---------- cartão aberto (um por bot e assunto) ----------

    async def cartao(
        self, usuario_id: UUID, agente_id: UUID, assunto: str
    ) -> dict[str, Any] | None:
        chave = CHAVE_CARTAO.format(usuario_id=usuario_id, agente_id=agente_id, assunto=assunto)
        bruto = _texto(await self.redis.get(chave))
        try:
            return json.loads(bruto) if bruto else None
        except ValueError:
            return None

    async def guardar_cartao(
        self,
        usuario_id: UUID,
        agente_id: UUID,
        assunto: str,
        aprovacao_id: UUID,
        validade_s: int,
        *,
        vinculado: bool = False,
    ) -> None:
        """``vinculado``: um turno pausou neste cartão (Vela-12); vencer vale como recusa."""
        chave = CHAVE_CARTAO.format(usuario_id=usuario_id, agente_id=agente_id, assunto=assunto)
        dados: dict[str, Any] = {"id": str(aprovacao_id), "desde": time.time()}
        if vinculado:
            dados["vinculado"] = True
        await self.redis.set(chave, json.dumps(dados), ex=validade_s)

    async def esquecer_cartao(self, usuario_id: UUID, agente_id: UUID, assunto: str) -> None:
        await self.redis.delete(
            CHAVE_CARTAO.format(usuario_id=usuario_id, agente_id=agente_id, assunto=assunto)
        )

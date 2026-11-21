"""Navegador do bot ao vivo (Farol-2, item 18 da etapa 6).

O que o usuário vê e faz na aba que o bot usa, sem sair do app:

- **Quadros.** Enquanto houver alguém assistindo (o app chama ``POST /v1/agentes/{id}/navegador/
  assistir`` a cada poucos segundos; a marca expira em ``VALIDADE_ASSISTINDO_S``), o worker tira
  uma captura da aba em uso do bot a cada ``PERIODO_S`` (menos de 1 s) e publica o evento SSE
  ``navegador.tela`` com uma miniatura JPEG. A captura inteira fica no Redis
  (``navegador:captura:<aba>``, com o dono em ``navegador:dono:<aba>``) para a rota
  ``GET /v1/navegador/abas/{aba_id}/captura``. Ninguém assistindo = nenhuma captura.
- **Assumir e agir.** Com a aba **assumida** (``POST …/assumir``, já existia), o usuário clica na
  imagem e digita. A API põe o pedido na fila ``navegador:comandos:<aba>`` (Redis); o worker que
  tem a aba o executa **só se a marca de assumida existir** e o pedido for do dono. O clique vem
  na escala da imagem que o usuário viu e é convertido para o tamanho real da janela da aba.
- **Segredo.** O texto digitado passa pela fila do Redis (vive ali alguns milissegundos e a fila
  expira) e é digitado na página: **nunca** vai para o rastro, para os eventos, para o log nem
  para o estado. O quadro seguinte mostra a página como o navegador a desenha (campo de senha
  aparece com pontos). Só se registra o tamanho do que foi digitado, e nem isso sai do worker.
  Exceção: com "Ensinar" ligado pelo próprio usuário (``app/navegador/ensinar.py``), o passo
  é anotado no Redis por até 30 min, com o texto mascarado (campo de senha vira ``[senha]``,
  dado pessoal vira ``[dado pessoal]``), para virar o rascunho de uma habilidade.
- **Devolver.** ``POST …/devolver`` solta a marca; a aba volta a ser do bot na próxima
  ferramenta (``AmbienteNavegador._sincronizar_assuncao``).

Cuidados: o stream do usuário guarda eventos por 24 h; um quadro por segundo ocuparia gigabytes.
Por isso só os últimos ``QUADROS_RETIDOS`` quadros de cada aba ficam no stream (os mais velhos
são apagados com ``XDEL``). Quadro igual ao anterior vai **sem** miniatura (``mudou: false``):
mantém o ritmo e o app segue com a imagem que já tem.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import io
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.redacao import limpar_texto_sensivel, url_sem_segredos
from app.eventos.tipos import EventoBase
from app.ferramentas.base import ErroFerramenta
from app.navegador import ensinar
from app.navegador.abas import Aba, GerenteAbas

registro = logging.getLogger(__name__)

CHAVE_ASSISTINDO = "navegador:assistindo:{agente_id}"
CHAVE_CAPTURA = "navegador:captura:{aba_id}"
CHAVE_DONO = "navegador:dono:{aba_id}"
CHAVE_ASSUMIDA = "navegador:assumida:{aba_id}"
FILA_COMANDOS = "navegador:comandos:{aba_id}"

VALIDADE_ASSISTINDO_S = 12
VALIDADE_CAPTURA_S = 120
VALIDADE_FILA_S = 30
"""Pedido que ninguém executou (worker parado) some da fila em 30 s."""
MAX_FILA = 50
PERIODO_S = 0.9
LARGURA_MINIATURA = 640
MAX_MINIATURA_BYTES = 64 * 1024
QUALIDADE_QUADRO = 70
QUALIDADE_MINIATURA = 50
QUADROS_RETIDOS = 3
MAX_TEXTO = 500
PRAZO_CAPTURA_MS = 3_000

TECLAS = frozenset(
    {
        "Enter",
        "Tab",
        "Escape",
        "Backspace",
        "Delete",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "PageUp",
        "PageDown",
    }
)

Publicar = Callable[[Any, UUID], Awaitable[str | None]]


class TelaNavegadorEvento(EventoBase):
    """Um quadro da aba que o usuário está assistindo (``GET /v1/eventos``)."""

    evento: ClassVar[Literal["navegador.tela"]] = "navegador.tela"
    aba_id: UUID
    agente_id: UUID
    url: str
    titulo: str
    largura: int = Field(description="Largura real da janela da aba (px).")
    altura: int
    miniatura: str | None = Field(
        default=None,
        description="data:image/jpeg;base64,… (até 640 px de largura); nulo se igual à anterior.",
    )
    mudou: bool = True
    assumida_pelo_usuario: bool = False
    aviso: str | None = None
    em: datetime


# ---------- pedidos do usuário ----------


class Comando(BaseModel):
    """Um pedido do usuário para a aba assumida. ``texto`` nunca é registrado em lugar nenhum."""

    tipo: Literal["clicar", "digitar", "tecla", "rolar"]
    usuario_id: UUID
    x: int | None = Field(default=None, ge=0, le=20_000)
    y: int | None = Field(default=None, ge=0, le=20_000)
    largura: int | None = Field(default=None, ge=1, le=20_000)
    altura: int | None = Field(default=None, ge=1, le=20_000)
    texto: str | None = Field(default=None, max_length=MAX_TEXTO, repr=False)
    tecla: str | None = None
    dy: int | None = Field(default=None, ge=-5_000, le=5_000)

    def __repr__(self) -> str:  # nunca mostra o texto, nem em log nem em traceback
        return f"Comando({self.tipo})"


def converter_ponto(
    x: int, y: int, largura_imagem: int, altura_imagem: int, janela: tuple[int, int]
) -> tuple[float, float]:
    """Ponto na escala da imagem que o usuário viu → ponto na janela real da aba."""
    largura, altura = janela
    return x * largura / largura_imagem, y * altura / altura_imagem


def validar_comando(comando: Comando) -> None:
    """Confere os campos que cada tipo exige (a API e o worker usam a mesma regra)."""
    if comando.tipo == "clicar":
        faltando = None in (comando.x, comando.y, comando.largura, comando.altura)
        if faltando or comando.x >= comando.largura or comando.y >= comando.altura:  # type: ignore[operator]
            raise ErroFerramenta("O clique precisa de x e y dentro da imagem (e do tamanho dela).")
    elif comando.tipo == "digitar":
        if not comando.texto:
            raise ErroFerramenta("Informe o texto.")
    elif comando.tipo == "tecla":
        if comando.tecla not in TECLAS:
            raise ErroFerramenta("Tecla não permitida. Use: " + ", ".join(sorted(TECLAS)) + ".")
    elif comando.dy is None or comando.dy == 0:
        raise ErroFerramenta("Informe dy (pixels para rolar; negativo sobe).")


def miniatura_do_quadro(jpeg: bytes) -> str | None:
    """JPEG reduzido (até 640 px) em ``data:`` URL; ``None`` se não couber no evento."""
    from PIL import Image

    with Image.open(io.BytesIO(jpeg)) as aberta:
        imagem = aberta.convert("RGB")
    if imagem.width > LARGURA_MINIATURA:
        altura = max(1, round(imagem.height * LARGURA_MINIATURA / imagem.width))
        imagem = imagem.resize((LARGURA_MINIATURA, altura))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=QUALIDADE_MINIATURA, optimize=True)
    dados = saida.getvalue()
    if len(dados) > MAX_MINIATURA_BYTES:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(dados).decode()


# ---------- o worker ----------


class NavegadorAoVivo:
    def __init__(
        self,
        *,
        gerente: GerenteAbas,
        motor: Any,
        redis: Any,
        publicar: Publicar,
        salvar_aba: Callable[[Aba], Awaitable[None]] | None = None,
        periodo_s: float = PERIODO_S,
    ) -> None:
        self._gerente = gerente
        self._motor = motor
        self._redis = redis
        self._publicar = publicar
        self._salvar_aba = salvar_aba
        self._periodo_s = periodo_s
        self._ultimo_quadro: dict[UUID, str] = {}
        self._ids: dict[UUID, deque[str]] = {}
        self._tarefas: list[asyncio.Task[None]] = []

    # ---------- ciclo de vida ----------

    def iniciar(self) -> None:
        self._tarefas = [
            asyncio.create_task(self._loop_quadros(), name="navegador-quadros"),
            asyncio.create_task(self._loop_comandos(), name="navegador-comandos"),
        ]

    async def parar(self) -> None:
        for tarefa in self._tarefas:
            tarefa.cancel()
        for tarefa in self._tarefas:
            with contextlib.suppress(asyncio.CancelledError):
                await tarefa
        self._tarefas = []

    # ---------- quadros ----------

    def _carregada(self, aba: Aba) -> bool:
        if not aba.carregada:
            return False
        try:
            self._motor.pagina(aba)
        except ErroFerramenta:
            return False
        return True

    async def abas_assistidas(self) -> list[Aba]:
        """A aba que cada bot assistido está usando: a assumida pelo usuário, senão a mais
        recente. Só abas carregadas neste worker e só de bot que alguém está assistindo."""
        por_agente: dict[UUID, list[Aba]] = {}
        for aba in self._gerente.todas():
            if self._carregada(aba):
                por_agente.setdefault(aba.agente_id, []).append(aba)
        escolhidas: list[Aba] = []
        for agente_id, abas in por_agente.items():
            if not await self._redis.exists(CHAVE_ASSISTINDO.format(agente_id=agente_id)):
                continue
            # a marca de assumida mora no Redis (a API a grava); o registro da aba só a copia
            # quando uma ferramenta do bot roda
            assumida = [
                a for a in abas if await self._redis.exists(CHAVE_ASSUMIDA.format(aba_id=a.id))
            ]
            escolhidas.append(max(assumida or abas, key=lambda a: a.usada_em))
        return escolhidas

    async def _loop_quadros(self) -> None:
        while True:
            inicio = time.monotonic()
            try:
                self._esquecer_fechadas()
                abas = await self.abas_assistidas()
                if abas:
                    await asyncio.gather(*(self.quadro(aba) for aba in abas))
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                registro.warning("quadro do navegador falhou (%s)", type(erro).__name__)
            await asyncio.sleep(max(0.05, self._periodo_s - (time.monotonic() - inicio)))

    def _esquecer_fechadas(self) -> None:
        """Aba fechada não deixa assinatura nem ids de quadro para trás."""
        vivas = {aba.id for aba in self._gerente.todas()}
        for guardado in (self._ultimo_quadro, self._ids):
            for aba_id in [a for a in guardado if a not in vivas]:
                del guardado[aba_id]

    async def quadro(self, aba: Aba, *, aviso: str | None = None) -> None:
        """Captura a aba, guarda a captura inteira e publica o quadro."""
        try:
            pagina = self._motor.pagina(aba)
            jpeg = await pagina.screenshot(
                type="jpeg", quality=QUALIDADE_QUADRO, timeout=PRAZO_CAPTURA_MS
            )
            tamanho = pagina.viewport_size or {"width": 1280, "height": 720}
        except Exception as erro:  # página navegando ou fechada: o próximo quadro tenta de novo
            registro.debug("sem quadro da aba %s (%s)", aba.id, type(erro).__name__)
            return
        assinatura = hashlib.blake2b(jpeg, digest_size=8).hexdigest()
        mudou = self._ultimo_quadro.get(aba.id) != assinatura
        self._ultimo_quadro[aba.id] = assinatura
        agente = aba.agente_id
        pipe = self._redis.pipeline(transaction=False)
        pipe.set(
            CHAVE_CAPTURA.format(aba_id=aba.id),
            base64.b64encode(jpeg).decode(),
            ex=VALIDADE_CAPTURA_S,
        )
        pipe.set(CHAVE_DONO.format(aba_id=aba.id), str(aba.usuario_id), ex=VALIDADE_CAPTURA_S)
        await pipe.execute()
        assumida = bool(await self._redis.exists(CHAVE_ASSUMIDA.format(aba_id=aba.id)))
        evento = TelaNavegadorEvento(
            aba_id=aba.id,
            agente_id=agente,
            url=url_sem_segredos(aba.url),
            titulo=limpar_texto_sensivel(aba.titulo)[:200],
            largura=int(tamanho["width"]),
            altura=int(tamanho["height"]),
            miniatura=await asyncio.to_thread(miniatura_do_quadro, jpeg) if mudou else None,
            mudou=mudou,
            assumida_pelo_usuario=assumida,
            aviso=aviso,
            em=datetime.now(UTC),
        )
        id_evento = await self._publicar(evento, aba.usuario_id)
        await self._reter(aba, id_evento)

    async def _reter(self, aba: Aba, id_evento: str | None) -> None:
        """Só os últimos quadros ficam no stream do usuário (senão ele cresceria sem parar)."""
        if not id_evento:
            return
        from app.eventos.streams import canal_usuario

        fila = self._ids.setdefault(aba.id, deque())
        fila.append(id_evento)
        while len(fila) > QUADROS_RETIDOS:
            with contextlib.suppress(Exception):
                await self._redis.xdel(canal_usuario(aba.usuario_id), fila.popleft())

    # ---------- pedidos do usuário ----------

    async def _loop_comandos(self) -> None:
        while True:
            try:
                chaves = [FILA_COMANDOS.format(aba_id=a.id) for a in self._gerente.todas()]
                if not chaves:
                    await asyncio.sleep(0.5)
                    continue
                item = await self._redis.blpop(chaves, timeout=1)
                if item is None:
                    continue
                chave, bruto = item
                chave = chave.decode() if isinstance(chave, bytes) else chave
                aba_id = UUID(chave.rsplit(":", 1)[-1])
                await self.executar(aba_id, bruto)
            except asyncio.CancelledError:
                raise
            except Exception as erro:  # nunca o conteúdo: o pedido pode ter texto digitado
                registro.warning("pedido do usuário no navegador falhou (%s)", type(erro).__name__)
                await asyncio.sleep(0.2)

    async def executar(self, aba_id: UUID, bruto: str | bytes) -> bool:
        """Executa um pedido do usuário. ``False`` se foi descartado (sem erro para o usuário)."""
        aba = self._gerente.obter(aba_id)
        if aba is None:
            return False
        try:
            comando = Comando.model_validate_json(bruto)
            validar_comando(comando)
        except Exception:
            return False
        if comando.usuario_id != aba.usuario_id:
            return False
        if not await self._redis.exists(CHAVE_ASSUMIDA.format(aba_id=aba_id)):
            return False  # a aba não está com o usuário: só ele, e só depois de assumir
        if not self._carregada(aba):
            return False
        pagina = self._motor.pagina(aba)
        # "Ensinar" (Onda 3, ``app/navegador/ensinar.py``): com a gravação ligada, anota o passo.
        gravando = await ensinar.ensinando(self._redis, aba_id) is not None
        alvo: dict[str, Any] | None = None
        url_antes = aba.url
        if comando.tipo == "clicar":
            tamanho = pagina.viewport_size or {"width": 1280, "height": 720}
            x, y = converter_ponto(
                comando.x or 0,
                comando.y or 0,
                comando.largura or 1,
                comando.altura or 1,
                (int(tamanho["width"]), int(tamanho["height"])),
            )
            if gravando:
                alvo = await _descrever(pagina, ensinar.DESCREVER_PONTO_JS, [x, y])
            await pagina.mouse.click(x, y)
        elif comando.tipo == "digitar":
            if gravando:
                alvo = await _descrever(pagina, ensinar.DESCREVER_FOCO_JS)
            await pagina.keyboard.type(comando.texto or "")
        elif comando.tipo == "tecla":
            await pagina.keyboard.press(comando.tecla or "")
        else:
            await pagina.mouse.wheel(0, comando.dy or 0)
        await asyncio.sleep(0.2)  # o clique pode abrir outra página
        aviso = await self._depois_de_agir(aba)
        if gravando:
            await self._anotar(aba_id, comando, alvo, url_antes)
        await self.quadro(self._gerente.obter(aba_id) or aba, aviso=aviso)
        return True

    async def _anotar(
        self, aba_id: UUID, comando: Comando, alvo: dict[str, Any] | None, url_antes: str
    ) -> None:
        """Um passo da gravação de "Ensinar". O texto digitado só entra mascarado (nunca senha)."""
        try:
            if comando.tipo == "clicar":
                passo = ensinar.Passo(tipo="clicar", alvo=ensinar.descrever_alvo(alvo))
            elif comando.tipo == "digitar":
                passo = ensinar.Passo(
                    tipo="digitar",
                    alvo=ensinar.descrever_alvo(alvo) if alvo else None,
                    texto=ensinar.texto_seguro(
                        comando.texto or "", senha=bool(alvo and alvo.get("senha"))
                    ),
                )
            elif comando.tipo == "tecla":
                passo = ensinar.Passo(tipo="tecla", texto=comando.tecla)
            else:
                passo = None
            if passo is not None:
                await ensinar.gravar(self._redis, aba_id, passo)
            atual = self._gerente.obter(aba_id)
            if atual is not None and atual.url and atual.url != url_antes:
                url = url_sem_segredos(atual.url)[:500]
                await ensinar.gravar(self._redis, aba_id, ensinar.Passo(tipo="pagina", url=url))
        except Exception as erro:  # nunca o conteúdo: pode ter texto digitado
            registro.debug("não anotei o passo de Ensinar (%s)", type(erro).__name__)

    async def _depois_de_agir(self, aba: Aba) -> str | None:
        """Atualiza o registro da aba; navegação barrada pela revisão de domínio vira aviso."""
        aviso = None
        revisao = self._motor.consumir_revisao(aba)
        if revisao is not None:
            with contextlib.suppress(Exception):
                await self._motor.pagina(aba).goto(aba.url, wait_until="domcontentloaded")
            aviso = (
                f"O endereço {revisao.dominio} é um domínio novo e este perfil tem login salvo, "
                "então a navegação ficou parada. Peça ao bot para abrir esse endereço."
            )
        try:
            pagina = self._motor.pagina(aba)
            atual = self._gerente.sincronizar_pagina(
                aba.id, url=pagina.url, titulo=await pagina.title()
            )
            if self._salvar_aba is not None:
                await self._salvar_aba(atual)
        except Exception as erro:
            registro.debug("não atualizei a aba %s (%s)", aba.id, type(erro).__name__)
        return aviso


async def _descrever(pagina: Any, script: str, argumento: Any = None) -> dict[str, Any] | None:
    """Papel e nome do elemento (para "Ensinar"); ``None`` se a página não responder logo."""
    try:
        resultado = await asyncio.wait_for(pagina.evaluate(script, argumento), 1.5)
    except Exception:
        return None
    return resultado if isinstance(resultado, dict) else None


# ---------- do lado da API ----------


async def marcar_assistindo(redis: Any, agente_id: UUID) -> int:
    """O app está olhando o navegador deste bot: liga os quadros por ``VALIDADE_ASSISTINDO_S``."""
    await redis.set(CHAVE_ASSISTINDO.format(agente_id=agente_id), "1", ex=VALIDADE_ASSISTINDO_S)
    return VALIDADE_ASSISTINDO_S


async def enfileirar_comando(redis: Any, aba_id: UUID, comando: Comando) -> None:
    """Põe o pedido do usuário na fila da aba. A fila expira e tem tamanho máximo."""
    chave = FILA_COMANDOS.format(aba_id=aba_id)
    if await redis.llen(chave) >= MAX_FILA:
        raise ErroFerramenta("Muitos pedidos de uma vez. Espere a aba responder.")
    await redis.rpush(chave, json.dumps(comando.model_dump(mode="json"), ensure_ascii=False))
    await redis.expire(chave, VALIDADE_FILA_S)

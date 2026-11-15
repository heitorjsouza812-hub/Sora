"""Serviço do computador do bot: o ciclo observar → agir → conferir, a área de arquivos, a tela
ao vivo (evento + última captura no Redis) e as regras de uso.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0), já trazida para o
navegador por árvore (``docs/referencias/agent-desktop.md``): refs qualificadas pela leitura
(``@cN:jM``), ref velha recusada, conferência depois de agir. Nada copiado; aqui o alvo é uma
tela inteira (janelas e pixels), não o DOM.

Regras (``docs/computador-por-bot.md``):

- não roda em rotina sem supervisão;
- o alvo ``virtual`` segue o sandbox (``SANDBOX_PROVEDOR=docker``; em produção só com
  ``SANDBOX_DOCKER_HOST``);
- agir exige uma observação deste worker (coordenadas e refs valem para a tela vista);
- nunca digita o que parece senha ou chave; o texto digitado não vai para o evento.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.computador.eventos import MAX_MINIATURA_BYTES, TelaComputadorEvento
from app.computador.interface import (
    AcaoComputador,
    AcaoResolvida,
    Alvo,
    Computador,
    LeituraGuardada,
    Observacao,
    ProvedorComputadores,
    ler_ref,
    normalizar_tecla,
    parece_senha,
    ref_da_janela,
)
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta

CHAVE_CAPTURA = "computador:captura:{agente_id}"
"""Última captura PNG em base64."""
CHAVE_ESTADO = "computador:estado:{agente_id}"
CHAVE_USO = "computador:uso"
"""Hash agente_id → último uso (epoch). O desligamento por ociosidade lê daqui."""
VALIDADE_CAPTURA_S = 60 * 60
VALIDADE_ESTADO_S = 24 * 60 * 60
LARGURA_MINIATURA = 480
MAX_LEITURA_BYTES = 20_000
MAX_ENTREGA_BYTES = 10 * 1024 * 1024
"""Tamanho máximo de um arquivo levado do computador para a conversa (vira anexo)."""
ESPERA_DEPOIS_DE_AGIR_S = 0.4
MAX_CAPTURAS_ESTAVEIS = 3

SEM_SUPERVISAO = "O computador do bot não roda em rotinas sem supervisão."
DESLIGADO = "O computador virtual está desligado neste servidor."
SENHA = (
    "Não digito senhas, chaves nem códigos de acesso. Peça ao usuário para entrar ele mesmo "
    "ou siga sem isso."
)

Publicar = Callable[[TelaComputadorEvento, UUID], Awaitable[None]]
GuardarAnexo = Callable[[ContextoFerramenta, str, bytes], Awaitable[UUID]]


def miniatura(png: bytes) -> str | None:
    """JPEG reduzido em data URL para o evento; ``None`` se não couber."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as imagem:
        imagem = imagem.convert("RGB")
        if imagem.width > LARGURA_MINIATURA:
            altura = max(1, round(imagem.height * LARGURA_MINIATURA / imagem.width))
            imagem = imagem.resize((LARGURA_MINIATURA, altura))
        saida = io.BytesIO()
        imagem.save(saida, format="JPEG", quality=55, optimize=True)
    dados = saida.getvalue()
    if len(dados) > MAX_MINIATURA_BYTES:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(dados).decode()


def rotulo_da_acao(acao: AcaoComputador) -> str:
    """Rótulo para a tela ao vivo. O texto digitado nunca aparece."""
    ponto = f" em {acao.x},{acao.y}" if acao.x is not None else ""
    if acao.tipo == "digitar":
        return f"Digitou {len(acao.texto or '')} caracteres"
    if acao.tipo == "tecla":
        return f"Tecla {acao.tecla}"
    if acao.tipo == "rolar":
        return f"Rolou para {acao.direcao}"
    if acao.tipo == "arrastar":
        return f"Arrastou de {acao.x},{acao.y} até {acao.ate_x},{acao.ate_y}"
    if acao.tipo == "abrir":
        return f"Abriu o {acao.programa}"
    nomes = {"clicar": "Clicou", "clique_duplo": "Clique duplo", "clicar_direito": "Botão direito"}
    return nomes.get(acao.tipo, acao.tipo) + (ponto or (f" em {acao.ref}" if acao.ref else ""))


def _titulo_seguro(titulo: str) -> str:
    from app.core.redacao import limpar_texto_sensivel

    return limpar_texto_sensivel(titulo)[:120]


TITULO_COM_TEXTO = "(janela com o texto digitado pelo bot)"
MIN_MARCA_DIGITADO = 4
MAX_MARCA_DIGITADO = 16


def _so_letras(texto: str) -> str:
    return "".join(c for c in texto.lower() if c.isalnum())


def marca_do_digitado(texto: str) -> str | None:
    """Começo do texto digitado, só letras e números (o Bloco de Notas tira ":" do título)."""
    marca = _so_letras(texto)[:MAX_MARCA_DIGITADO]
    return marca if len(marca) >= MIN_MARCA_DIGITADO else None


def titulo_sem_digitado(titulo: str, marcas: list[str]) -> str:
    """Editores põem a primeira linha do documento no título (Bloco de Notas): o título da janela
    ativa não pode levar para o rastro o que o bot digitou (Vela-6, C3)."""
    normalizado = _so_letras(titulo)
    if any(m in normalizado for m in marcas):
        return TITULO_COM_TEXTO
    return _titulo_seguro(titulo)


@dataclass(slots=True)
class ServicoComputador:
    provedores: dict[Alvo, ProvedorComputadores]
    redis: Any
    publicar: Publicar
    virtual_ativo: Callable[[], bool] = lambda: True
    guardar_anexo: GuardarAnexo | None = None
    """Grava um arquivo do computador como anexo (``computador_entregar_arquivo``)."""
    leituras: dict[tuple[UUID, Alvo], LeituraGuardada] = field(default_factory=dict)
    _travas: dict[UUID, asyncio.Lock] = field(default_factory=dict)
    _digitados: dict[tuple[UUID, Alvo], list[str]] = field(default_factory=dict)
    """Só a marca (começo normalizado) dos últimos textos digitados, em memória: tira o texto
    do título da janela ativa no evento ``computador.tela``."""

    # ---------- regras ----------

    def _conferir(self, contexto: ContextoFerramenta, alvo: Alvo) -> ProvedorComputadores:
        if contexto.sem_supervisao:
            raise ErroFerramenta(SEM_SUPERVISAO)
        if alvo is Alvo.VIRTUAL and not self.virtual_ativo():
            raise ErroFerramenta(DESLIGADO)
        provedor = self.provedores.get(alvo)
        if provedor is None:
            raise ErroFerramenta("Esse computador não está disponível.")
        return provedor

    def _trava(self, agente_id: UUID) -> asyncio.Lock:
        return self._travas.setdefault(agente_id, asyncio.Lock())

    async def _computador(self, contexto: ContextoFerramenta, alvo: Alvo) -> Computador:
        provedor = self._conferir(contexto, alvo)
        computador = await provedor.obter(contexto.usuario_id, contexto.agente_id)
        await self.redis.hset(CHAVE_USO, str(contexto.agente_id), str(time.time()))
        return computador

    # ---------- observar ----------

    def _guardar(self, agente_id: UUID, alvo: Alvo, observacao: Observacao) -> LeituraGuardada:
        anterior = self.leituras.get((agente_id, alvo))
        geracao = (anterior.geracao if anterior else 0) + 1
        refs = {ref_da_janela(geracao, i): j for i, j in enumerate(observacao.janelas, start=1)}
        leitura = LeituraGuardada(geracao=geracao, observacao=observacao, refs=refs)
        self.leituras[(agente_id, alvo)] = leitura
        return leitura

    async def _registrar_tela(
        self,
        contexto: ContextoFerramenta,
        alvo: Alvo,
        leitura: LeituraGuardada,
        *,
        acao: str | None = None,
        mudou: bool | None = None,
    ) -> None:
        tela = leitura.observacao.tela
        ativa = next((j for j in leitura.observacao.janelas if j.ativa), None)
        agora = datetime.now(UTC)
        estado = {
            "agente_id": str(contexto.agente_id),
            "alvo": alvo.value,
            "ligado": True,
            "geracao": leitura.geracao,
            "largura": tela.largura,
            "altura": tela.altura,
            "janela_ativa": _titulo_seguro(ativa.programa or "Programa do computador")
            if ativa and alvo == Alvo.PC_USUARIO
            else titulo_sem_digitado(
                ativa.titulo, self._digitados.get((contexto.agente_id, alvo), [])
            )
            if ativa
            else None,
            "acao": acao,
            "atualizado_em": agora.isoformat(),
        }
        agente = contexto.agente_id
        pipe = self.redis.pipeline(transaction=False)
        # base64: o cliente Redis da API devolve texto (decode_responses)
        captura = base64.b64encode(tela.png).decode()
        pipe.set(CHAVE_CAPTURA.format(agente_id=agente), captura, ex=VALIDADE_CAPTURA_S)
        pipe.set(CHAVE_ESTADO.format(agente_id=agente), json.dumps(estado), ex=VALIDADE_ESTADO_S)
        await pipe.execute()
        await self.publicar(
            TelaComputadorEvento(
                agente_id=agente,
                alvo=alvo.value,
                ligado=True,
                geracao=leitura.geracao,
                largura=tela.largura,
                altura=tela.altura,
                miniatura=await asyncio.to_thread(miniatura, tela.png),
                janela_ativa=estado["janela_ativa"],
                acao=acao,
                mudou=mudou,
                em=agora,
            ),
            contexto.usuario_id,
        )

    @staticmethod
    def descrever(leitura: LeituraGuardada, alvo: Alvo) -> str:
        from app.agentes.prompts import cercar

        tela = leitura.observacao.tela
        nome = "Computador virtual" if alvo is Alvo.VIRTUAL else "Computador do usuário"
        linhas = []
        for ref, janela in leitura.refs.items():
            ativa = " (ativa)" if janela.ativa else ""
            linhas.append(
                f"- {ref} {janela.titulo!r} em ({janela.x},{janela.y}) "
                f"{janela.largura}x{janela.altura}{ativa}"
            )
        janelas = "\n".join(linhas) or "(nenhuma janela aberta: use abrir navegador ou terminal)"
        arvore = ""
        if leitura.observacao.arvore:
            arvore = (
                "\n\nElementos:\n"
                + json.dumps(leitura.observacao.arvore, ensure_ascii=False)[:8_000]
            )
        return (
            f"{nome} ({tela.largura}x{tela.altura} px), leitura @c{leitura.geracao}. "
            "Coordenadas x/y são pixels desta captura; refs @cN:jM valem só para esta leitura.\n"
            "A tela aparece ao vivo para o usuário no painel Trabalho.\n\n"
            + cercar(f"Janelas:\n{janelas}{arvore}", "computador")
        )

    async def observar(self, contexto: ContextoFerramenta, alvo: Alvo = Alvo.VIRTUAL) -> str:
        async with self._trava(contexto.agente_id):
            computador = await self._computador(contexto, alvo)
            leitura = self._guardar(contexto.agente_id, alvo, await computador.observar())
            await self._registrar_tela(contexto, alvo, leitura, acao="Observou a tela")
            return self.descrever(leitura, alvo)

    # ---------- agir ----------

    @staticmethod
    def resolver(acao: AcaoComputador, leitura: LeituraGuardada) -> AcaoResolvida:
        tela = leitura.observacao.tela
        janela = None
        if acao.ref:
            geracao, _ = ler_ref(acao.ref)
            if geracao != leitura.geracao:
                raise ErroFerramenta(
                    "Essa ref é de uma leitura antiga da tela. Use computador_observar de novo."
                )
            janela = leitura.refs.get(acao.ref)
            if janela is None:
                raise ErroFerramenta(f"A ref {acao.ref} não existe na última leitura.")
        for x, y in ((acao.x, acao.y), (acao.ate_x, acao.ate_y)):
            if x is not None and y is not None and not (x < tela.largura and y < tela.altura):
                raise ErroFerramenta(
                    f"O ponto {x},{y} está fora da tela ({tela.largura}x{tela.altura})."
                )
        if acao.tipo == "digitar" and parece_senha(acao.texto or ""):
            raise ErroFerramenta(SENHA)
        tecla = normalizar_tecla(acao.tecla or "") if acao.tipo == "tecla" else None
        ponto = (acao.x, acao.y) if acao.x is not None and acao.y is not None else None
        if ponto is None and janela is not None and acao.tipo != "digitar":
            ponto = janela.centro
        return AcaoResolvida(acao=acao, janela=janela, tecla=tecla, ponto=ponto)

    async def _observar_estavel(self, computador: Computador) -> Observacao:
        """Espera a tela parar de mudar (até 3 capturas) e devolve a última."""
        await asyncio.sleep(ESPERA_DEPOIS_DE_AGIR_S)
        atual = await computador.observar()
        for _ in range(MAX_CAPTURAS_ESTAVEIS - 1):
            await asyncio.sleep(ESPERA_DEPOIS_DE_AGIR_S)
            nova = await computador.observar()
            if nova.tela.assinatura == atual.tela.assinatura:
                return nova
            atual = nova
        return atual

    async def agir(
        self, contexto: ContextoFerramenta, acoes: list[AcaoComputador], alvo: Alvo = Alvo.VIRTUAL
    ) -> str:
        async with self._trava(contexto.agente_id):
            self._conferir(contexto, alvo)  # regras antes de tudo
            leitura = self.leituras.get((contexto.agente_id, alvo))
            if leitura is None:
                raise ErroFerramenta(
                    "Observe a tela antes de agir (computador_observar): coordenadas e refs "
                    "valem para a tela que você viu."
                )
            resolvidas = [self.resolver(acao, leitura) for acao in acoes]  # tudo antes de agir
            marcas = self._digitados.setdefault((contexto.agente_id, alvo), [])
            for resolvida in resolvidas:
                marca = marca_do_digitado(resolvida.acao.texto or "")
                if resolvida.acao.tipo == "digitar" and marca and marca not in marcas:
                    marcas.append(marca)
            del marcas[:-10]
            computador = await self._computador(contexto, alvo)
            antes = leitura.observacao
            feitas = 0
            falha: str | None = None
            for resolvida in resolvidas:
                try:
                    await computador.agir(resolvida)
                except ErroFerramenta as erro:
                    falha = (
                        f"A ação {feitas + 1} ({resolvida.acao.tipo}) falhou depois de {feitas} "
                        f"feita(s): {erro} Não repita as que já foram feitas."
                    )
                    break
                feitas += 1
                await asyncio.sleep(0.15)
            depois = await self._observar_estavel(computador)
            nova = self._guardar(contexto.agente_id, alvo, depois)
            mudou = depois.tela.assinatura != antes.tela.assinatura
            rotulo = "; ".join(rotulo_da_acao(r.acao) for r in resolvidas[: max(feitas, 1)])
            await self._registrar_tela(contexto, alvo, nova, acao=rotulo, mudou=mudou)
            conferencia = (
                "Conferência: a tela mudou depois da ação."
                if mudou
                else "Conferência: a tela NÃO mudou. A ação pode não ter tido efeito; confira "
                "antes de repetir."
            )
            texto = f"{feitas} de {len(resolvidas)} ação(ões) feita(s). {conferencia}\n\n"
            texto += self.descrever(nova, alvo)
            if falha:
                raise ErroFerramenta(f"{falha}\n\n{texto}")
            return texto

    # ---------- arquivos ----------

    async def arquivos(
        self,
        contexto: ContextoFerramenta,
        operacao: str,
        caminho: str,
        alvo: Alvo = Alvo.VIRTUAL,
    ) -> str:
        async with self._trava(contexto.agente_id):
            computador = await self._computador(contexto, alvo)
            if operacao == "listar":
                itens = await computador.listar_arquivos(caminho)
                if not itens:
                    return "A pasta está vazia. Downloads do navegador caem aqui."
                return "\n".join(
                    f"- {'📁' if i.tipo == 'pasta' else '📄'} {i.caminho}"
                    + (f" ({i.tamanho} bytes)" if i.tipo == "arquivo" else "")
                    for i in itens
                )
            dados = await computador.ler_arquivo(caminho, MAX_LEITURA_BYTES)
        from app.agentes.prompts import cercar

        cortado = len(dados) > MAX_LEITURA_BYTES
        texto = dados[:MAX_LEITURA_BYTES].decode(errors="replace")
        aviso = f"\n[… cortado em {MAX_LEITURA_BYTES} bytes]" if cortado else ""
        return cercar(texto + aviso, f"computador:{caminho}")

    async def escrever(
        self, contexto: ContextoFerramenta, caminho: str, conteudo: str, alvo: Alvo = Alvo.VIRTUAL
    ) -> str:
        async with self._trava(contexto.agente_id):
            computador = await self._computador(contexto, alvo)
            await computador.escrever_arquivo(caminho, conteudo.encode())
        return f"Gravei {caminho} na sua área de arquivos ({len(conteudo.encode())} bytes)."

    async def entregar(
        self, contexto: ContextoFerramenta, caminho: str, alvo: Alvo = Alvo.VIRTUAL
    ) -> str:
        """Leva um arquivo da área do bot para a conversa como anexo (sobrevive ao desligar)."""
        if self.guardar_anexo is None:
            raise ErroFerramenta("Este servidor não guarda arquivos do computador.")
        async with self._trava(contexto.agente_id):
            computador = await self._computador(contexto, alvo)
            dados = await computador.ler_arquivo(caminho, MAX_ENTREGA_BYTES)
        if len(dados) > MAX_ENTREGA_BYTES:
            raise ErroFerramenta(
                f"O arquivo passa de {MAX_ENTREGA_BYTES // (1024 * 1024)} MB: divida em partes."
            )
        if not dados:
            raise ErroFerramenta("O arquivo está vazio.")
        nome = caminho.replace("\\", "/").rsplit("/", 1)[-1] or "arquivo"
        anexo_id = await self.guardar_anexo(contexto, nome, dados)
        return (
            f"Arquivo {nome} guardado como anexo (anexo_id: {anexo_id}, {len(dados)} bytes). "
            "Ele vai junto com a sua próxima mensagem ao usuário e não some quando o computador "
            "desligar."
        )

    async def desligar(self, contexto: ContextoFerramenta, alvo: Alvo = Alvo.VIRTUAL) -> str:
        provedor = self._conferir(contexto, alvo)
        async with self._trava(contexto.agente_id):
            desligado = await provedor.desligar(contexto.agente_id)
            self.leituras.pop((contexto.agente_id, alvo), None)
        await marcar_desligado(self.redis, self.publicar, contexto.agente_id, contexto.usuario_id)
        return (
            "Computador desligado. A área de arquivos foi apagada."
            if desligado
            else "O computador já estava desligado."
        )


async def marcar_desligado(
    redis: Any, publicar: Publicar, agente_id: UUID, usuario_id: UUID
) -> None:
    pipe = redis.pipeline(transaction=False)
    pipe.delete(CHAVE_CAPTURA.format(agente_id=agente_id))
    pipe.delete(CHAVE_ESTADO.format(agente_id=agente_id))
    pipe.hdel(CHAVE_USO, str(agente_id))
    await pipe.execute()
    await publicar(
        TelaComputadorEvento(
            agente_id=agente_id, alvo="virtual", ligado=False, em=datetime.now(UTC)
        ),
        usuario_id,
    )

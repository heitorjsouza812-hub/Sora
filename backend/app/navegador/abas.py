"""Abas do navegador persistente: elas sobrevivem ao turno, e só o agente (ou o usuário) fecha.

Regras da Sora:

- uma aba pertence a um agente e mora na partição do perfil dele (``app/navegador/perfis.py``);
  ela continua aberta depois do turno, para o próximo turno seguir de onde parou e o usuário
  ver o resultado. Fechar é decisão do agente (``navegador_fechar_aba``) ou do usuário;
- o usuário pode **assumir** uma aba (fazer login, resolver um captcha, conferir algo). Enquanto
  ele segura a aba, nenhuma ferramenta de agente toca nela — nem para fechar;
- aba parada há 30 min (5 min com pouca memória) é **descarregada**: o registro fica, a página
  sai da memória e recarrega no próximo uso;
- apagar o agente fecha as abas dele e limpa a partição "só deste agente"; trocar o perfil do
  agente fecha as abas dele (as novas abrem no perfil novo; o antigo guarda os dados);
- ao reiniciar, as abas voltam cada uma na partição salva; partição inválida é descartada;
- inspecionar: captura de tela (vira anexo) e as últimas mensagens do console, já redigidas.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.redacao import limpar_texto_sensivel, url_sem_segredos
from app.ferramentas.base import ErroFerramenta
from app.navegador.perfis import EscolhaPerfil, particao, particao_valida

MAX_ABAS_POR_AGENTE = 8
MAX_ABAS_POR_USUARIO = 30
OCIOSA_APOS = timedelta(minutes=30)
OCIOSA_APOS_POUCA_MEMORIA = timedelta(minutes=5)
MAX_LINHAS_CONSOLE = 200
MAX_TEXTO_CONSOLE = 500


def _agora() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LinhaConsole:
    nivel: Literal["log", "info", "warning", "error"]
    texto: str
    momento: datetime = field(default_factory=_agora)


@dataclass(frozen=True, slots=True)
class Aba:
    id: UUID
    usuario_id: UUID
    agente_id: UUID
    particao: str
    url: str = "about:blank"
    titulo: str = ""
    aberta_em: datetime = field(default_factory=_agora)
    usada_em: datetime = field(default_factory=_agora)
    carregada: bool = True
    assumida_pelo_usuario: bool = False


class Motor(Protocol):
    """Quem abre páginas de verdade (Playwright no servidor; um falso nos testes)."""

    async def abrir_pagina(self, aba: Aba) -> None: ...
    async def navegar(self, aba: Aba, url: str) -> tuple[str, str]: ...
    async def descarregar(self, aba: Aba) -> None: ...
    async def fechar(self, aba: Aba) -> None: ...
    async def capturar(self, aba: Aba) -> bytes: ...
    async def limpar_particao(self, particao_: str) -> None: ...


class GerenteAbas:
    def __init__(self, motor: Motor) -> None:
        self._motor = motor
        self._abas: dict[UUID, Aba] = {}
        self._console: dict[UUID, deque[LinhaConsole]] = {}

    # ---------- abrir e usar ----------

    async def abrir(
        self, *, usuario_id: UUID, agente_id: UUID, escolha: EscolhaPerfil, url: str | None = None
    ) -> Aba:
        do_agente = self.do_agente(agente_id)
        if len(do_agente) >= MAX_ABAS_POR_AGENTE:
            raise ErroFerramenta(
                f"Você já tem {MAX_ABAS_POR_AGENTE} abas abertas. Feche as que não usa mais "
                "com navegador_fechar_aba."
            )
        da_conta = sum(1 for a in self._abas.values() if a.usuario_id == usuario_id)
        if da_conta >= MAX_ABAS_POR_USUARIO:
            raise ErroFerramenta("A conta chegou ao limite de abas abertas.")
        aba = Aba(
            id=uuid4(),
            usuario_id=usuario_id,
            agente_id=agente_id,
            particao=particao(usuario_id, agente_id, escolha),
        )
        await self._motor.abrir_pagina(aba)
        self._abas[aba.id] = aba
        self._console[aba.id] = deque(maxlen=MAX_LINHAS_CONSOLE)
        if url:
            aba = await self.navegar(aba.id, agente_id, url)
        return aba

    def exigir(self, aba_id: UUID, agente_id: UUID) -> Aba:
        """O ponto por onde **toda** ferramenta de agente passa antes de mexer numa aba."""
        aba = self._abas.get(aba_id)
        if aba is None or aba.agente_id != agente_id:
            raise ErroFerramenta("Essa aba não existe ou não é sua. Use navegador_abas.")
        if aba.assumida_pelo_usuario:
            raise ErroFerramenta(
                "O usuário está usando esta aba agora. Espere ele devolver ou use outra aba."
            )
        return aba

    async def navegar(self, aba_id: UUID, agente_id: UUID, url: str) -> Aba:
        aba = await self._garantir_carregada(self.exigir(aba_id, agente_id))
        url_final, titulo = await self._motor.navegar(aba, url)
        return self._gravar(replace(aba, url=url_final, titulo=titulo[:200], usada_em=_agora()))

    async def usar(self, aba_id: UUID, agente_id: UUID) -> Aba:
        """Antes de ler ou agir: recarrega se foi descarregada e marca o uso."""
        aba = await self._garantir_carregada(self.exigir(aba_id, agente_id))
        return self._gravar(replace(aba, usada_em=_agora()))

    async def fechar(self, aba_id: UUID, agente_id: UUID) -> None:
        aba = self.exigir(aba_id, agente_id)
        await self._remover(aba)

    def do_agente(self, agente_id: UUID) -> list[Aba]:
        return sorted(
            (a for a in self._abas.values() if a.agente_id == agente_id), key=lambda a: a.aberta_em
        )

    def descrever(self, agente_id: UUID) -> str:
        abas = self.do_agente(agente_id)
        if not abas:
            return "Você não tem abas abertas. Use navegador_abrir."
        linhas = []
        for aba in abas:
            marcas = []
            if aba.assumida_pelo_usuario:
                marcas.append("o usuário está usando")
            if not aba.carregada:
                marcas.append("descarregada, recarrega ao usar")
            sufixo = f" ({'; '.join(marcas)})" if marcas else ""
            titulo = aba.titulo or "sem título"
            linhas.append(f"- {aba.id}: {titulo} — {url_sem_segredos(aba.url)}{sufixo}")
        return "Suas abas:\n" + "\n".join(linhas)

    # ---------- usuário ----------

    def assumir(self, aba_id: UUID, usuario_id: UUID) -> Aba:
        aba = self._da_conta(aba_id, usuario_id)
        return self._gravar(replace(aba, assumida_pelo_usuario=True))

    def devolver(self, aba_id: UUID, usuario_id: UUID) -> Aba:
        aba = self._da_conta(aba_id, usuario_id)
        return self._gravar(replace(aba, assumida_pelo_usuario=False, usada_em=_agora()))

    async def fechar_pelo_usuario(self, aba_id: UUID, usuario_id: UUID) -> None:
        await self._remover(self._da_conta(aba_id, usuario_id))

    # ---------- inspecionar ----------

    async def capturar(self, aba_id: UUID, agente_id: UUID) -> bytes:
        aba = await self.usar(aba_id, agente_id)
        return await self._motor.capturar(aba)

    def anotar_console(self, aba_id: UUID, nivel: str, texto: str) -> None:
        """O motor chama a cada mensagem do console da página."""
        registro = self._console.get(aba_id)
        if registro is None:
            return
        nivel_ok: Literal["log", "info", "warning", "error"] = (
            nivel if nivel in ("log", "info", "warning", "error") else "log"  # type: ignore[assignment]
        )
        limpo = limpar_texto_sensivel(" ".join(texto.split()))[:MAX_TEXTO_CONSOLE]
        registro.append(LinhaConsole(nivel_ok, limpo))

    def console(
        self, aba_id: UUID, agente_id: UUID, *, so_erros: bool = False, limite: int = 50
    ) -> list[LinhaConsole]:
        self.exigir(aba_id, agente_id)
        linhas = list(self._console.get(aba_id, ()))
        if so_erros:
            linhas = [linha for linha in linhas if linha.nivel in ("warning", "error")]
        return linhas[-max(1, min(limite, MAX_LINHAS_CONSOLE)) :]

    # ---------- manutenção ----------

    async def descarregar_ociosas(
        self, *, agora: datetime | None = None, pouca_memoria: bool = False
    ) -> list[UUID]:
        agora = agora or _agora()
        limite = OCIOSA_APOS_POUCA_MEMORIA if pouca_memoria else OCIOSA_APOS
        descarregadas = []
        for aba in list(self._abas.values()):
            if aba.carregada and not aba.assumida_pelo_usuario and agora - aba.usada_em >= limite:
                await self._motor.descarregar(aba)
                self._gravar(replace(aba, carregada=False))
                descarregadas.append(aba.id)
        return descarregadas

    async def agente_apagado(self, agente_id: UUID, particao_propria: str | None) -> int:
        abas = self.do_agente(agente_id)
        for aba in abas:
            await self._remover(aba)
        if particao_propria and "-agente-" in particao_propria:
            await self._motor.limpar_particao(particao_propria)
        return len(abas)

    async def perfil_trocado(self, agente_id: UUID) -> int:
        abas = [a for a in self.do_agente(agente_id) if not a.assumida_pelo_usuario]
        for aba in abas:
            await self._remover(aba)
        return len(abas)

    async def perfil_apagado(self, particao_: str) -> int:
        abas = [a for a in self._abas.values() if a.particao == particao_]
        for aba in abas:
            await self._remover(aba)
        await self._motor.limpar_particao(particao_)
        return len(abas)

    def para_salvar(self) -> list[Aba]:
        return list(self._abas.values())

    async def restaurar(
        self, abas: Sequence[Aba], *, perfis_por_usuario: dict[UUID, set[UUID]]
    ) -> list[Aba]:
        """Depois de reiniciar: volta as abas descarregadas, na partição salva de cada uma."""
        voltaram = []
        for aba in abas:
            if not particao_valida(
                aba.particao,
                usuario_id=aba.usuario_id,
                perfis_existentes=perfis_por_usuario.get(aba.usuario_id, set()),
            ):
                continue
            restaurada = replace(aba, carregada=False, assumida_pelo_usuario=False)
            self._abas[restaurada.id] = restaurada
            self._console[restaurada.id] = deque(maxlen=MAX_LINHAS_CONSOLE)
            voltaram.append(restaurada)
        return voltaram

    # ---------- interno ----------

    async def _garantir_carregada(self, aba: Aba) -> Aba:
        if aba.carregada:
            return aba
        await self._motor.abrir_pagina(aba)
        if aba.url and aba.url != "about:blank":
            url_final, titulo = await self._motor.navegar(aba, aba.url)
            aba = replace(aba, url=url_final, titulo=titulo[:200])
        return self._gravar(replace(aba, carregada=True))

    def _da_conta(self, aba_id: UUID, usuario_id: UUID) -> Aba:
        aba = self._abas.get(aba_id)
        if aba is None or aba.usuario_id != usuario_id:
            raise ErroFerramenta("Aba não encontrada.")
        return aba

    def _gravar(self, aba: Aba) -> Aba:
        self._abas[aba.id] = aba
        return aba

    async def _remover(self, aba: Aba) -> None:
        if self._abas.pop(aba.id, None) is None:
            return  # fechar duas vezes não faz mal
        self._console.pop(aba.id, None)
        if aba.carregada:
            await self._motor.fechar(aba)


# ---------- ferramentas novas (as de antes, navegador_ler/agir, ganham ``aba_id``) ----------


class NavegadorAbas(BaseModel):
    """Lista as suas abas abertas (continuam abertas entre um turno e outro)."""


class NavegadorFecharAba(BaseModel):
    """Fecha uma aba que você não precisa mais. Feche quando terminar a tarefa."""

    aba_id: UUID


class NavegadorCapturar(BaseModel):
    """Tira uma captura da tela da aba. A imagem vira anexo e você pode passar a um colega."""

    aba_id: UUID


class NavegadorConsole(BaseModel):
    """Lê as últimas mensagens do console da página (útil para entender erros do site)."""

    aba_id: UUID
    so_erros: bool = Field(default=True)
    limite: int = Field(default=30, ge=1, le=MAX_LINHAS_CONSOLE)


class NavegadorPedirAjuda(BaseModel):
    """Pede ao usuário para assumir a aba (login, captcha, confirmação). Espera ele devolver."""

    aba_id: UUID
    motivo: str = Field(min_length=3, max_length=300)

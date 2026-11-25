"""Alvo ``pc_usuario`` (C3): o PC do próprio usuário, só pelo app de desktop.

O bot usa as mesmas ferramentas do computador virtual (``computador_observar``/``computador_agir``
com ``alvo: "pc_usuario"``); o ciclo observar → agir → conferir continua em ``servico.py``. Aqui
fica só o alvo, que **não executa nada no servidor**: cada operação vira um comando para a ponte
do app de desktop (``pc_usuario_canal.py``; Rust em ``app/src-tauri/src/pc/``), que observa a tela
(captura + árvore de UI Automation), age com o mouse e o teclado e devolve o resultado.

Regras (``docs/computador-por-bot.md`` § C3), garantidas aqui **e** de novo na ponte:

- **desligado por padrão**: só funciona com o app de desktop aberto e logado nesta conta e com o
  bot ligado nele (Configurações → Computador). Sem isso: ``RECUSA``.
- **um bot por vez** (``CanalPc.pegar_vez``): os outros recebem "o PC está em uso por X";
- **primeira ação em cada programa** vira cartão "Precisa de você" (Permitir uma vez · Sempre
  permitir neste programa · Recusar), no sistema de aprovações (``pc_usuario_cartoes.py``);
- **mexer no mouse ou no teclado pausa** (a ponte detecta entrada física) e vira cartão para
  retomar; **Parar** (borda na tela) tira a vez do bot;
- **cartão pausa o turno** (Vela-12): no worker (com ``contexto``), o bot não espera o cartão
  dentro da ferramenta; ele liga o cartão ao turno (``Cartoes.vincular``) e o turno pausa
  (``interrupt``), como os cartões do revisor. "Permitir" põe na fila a retomada do mesmo turno,
  a ferramenta roda de novo e encontra o cartão decidido. Só pausa quando nada foi feito ainda
  nesta chamada (senão a retomada repetiria ações); aí devolve o erro e a próxima chamada pausa;
- nunca digita senha nem mexe em campo de senha; programas de senha, segurança do Windows, UAC,
  terminais e a própria Sora são bloqueados; o texto digitado nunca vai para o rastro;
- nada de arquivos do PC por aqui (só tela, mouse e teclado) e nunca em rotina sem supervisão
  (o serviço recusa antes).
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

from app.computador.interface import (
    MAX_COORDENADA,
    AcaoResolvida,
    Alvo,
    ArquivoArea,
    Janela,
    Observacao,
    Tela,
    parece_senha,
)
from app.computador.pc_usuario_canal import AgentePc, CanalPc, SemApp
from app.computador.pc_usuario_cartoes import FERRAMENTA_PROGRAMA, Cartoes, CartoesBanco
from app.ferramentas.base import ErroFerramenta

RECUSA = (
    "O controle do seu computador precisa do app de desktop da Sora aberto e logado nesta conta. "
    "Peça ao usuário para abrir o app de desktop da Sora no Windows e ligar o bot em "
    "Configurações → Computador. Informe que a ação no PC ficou pendente."
)
DESLIGADO_PARA_O_BOT = (
    "O usuário não ligou o controle do computador para este bot. Ele liga em Configurações → "
    "Computador, no app de desktop. Informe que a ação no PC ficou pendente."
)
PARADO = (
    "O usuário clicou em Parar: não use o computador dele de novo nesta tarefa. Diga o que "
    "ficou faltando."
)
RECUSOU_RETOMAR = (
    "O usuário preferiu ficar com o computador. Não use o PC dele de novo nesta tarefa; diga o "
    "que ficou faltando."
)
RETOMADO = (
    "O usuário mexeu no computador, o controle pausou e ele mandou retomar. A tela pode ter "
    "mudado: confira a captura nova antes de repetir a ação."
)
PAUSADO_ESPERANDO = (
    "Pausado: o usuário está usando o computador. Pedi para ele mandar retomar (cartão "
    "'Precisa de você'). Não tente usar o PC até ele responder; termine o turno avisando isso."
)
PROGRAMA_ESPERANDO = (
    "Pedi permissão ao usuário para usar {programa} (cartão 'Precisa de você') e ele ainda não "
    "respondeu. Não insista: termine o turno dizendo que precisa dessa permissão."
)
SENHA = (
    "Esse campo é de senha. Não digito nem mexo em campos de senha: peça ao usuário para fazer "
    "essa parte ele mesmo."
)
ABRIR = (
    "No computador do usuário a ação 'abrir' não existe: use computador_abrir_programa com o "
    "nome (Excel, Word, PowerPoint, Bloco de Notas, Paint, LibreOffice Calc ou Writer). Outro "
    "programa: peça ao usuário para abrir e deixar a janela na tela; depois observe de novo."
)
NAO_ABRIVEL = (
    "Esse programa não está na lista que eu abro pelo nome (Excel, Word, PowerPoint, Bloco de "
    "Notas, Paint, LibreOffice Calc ou Writer). Peça ao usuário para abrir e depois observe."
)
NAO_INSTALADO = (
    "{programa} não está instalado neste computador. Tente outro da lista (o LibreOffice Calc ou "
    "o Bloco de Notas servem para uma tabela simples) ou peça ao usuário."
)
PAUSOU_NO_MEIO = (
    "Pausei: o usuário mexeu no mouse ou no teclado durante a ação, que pode ter ficado pela "
    "metade. Chame computador_observar: eu espero o usuário mandar continuar e mostro a tela; "
    "confira antes de repetir qualquer coisa."
)
CARTAO_NA_FILA = (
    "Pedi ao usuário (cartão 'Precisa de você') para usar {programa}. As ações anteriores desta "
    "chamada já foram feitas. Chame de novo a mesma ação depois: eu espero a resposta dele."
)
TECLA_PROIBIDA = (
    "Essa tecla não é permitida no computador do usuário (menu Iniciar, Executar, troca de "
    "janela, Gerenciador de Tarefas ou ferramentas do desenvolvedor). Clique na janela que "
    "precisa ou peça ao usuário."
)
BLOQUEIO = (
    "Parei: {programa} abriu durante a sua ação, e programas como esse (terminal, scripts, "
    "registro, Gerenciador de Tarefas) são bloqueados para bots. O controle "
    "do computador ficou parado até o usuário decidir o cartão 'Precisa de você'. Não tente de "
    "novo; diga ao usuário o que estava fazendo."
)
CAPTURA_OMITIDA = (
    "A captura foi ocultada: um programa bloqueado (senhas, segurança, terminal ou a própria "
    "Sora) está na frente ou cobre a maior parte da tela. Peça ao usuário para trocar de janela."
)
ARQUIVOS = (
    "No computador do usuário não leio nem gravo arquivos direto: só tela, mouse e teclado. "
    "Para arquivos, use o computador virtual (alvo virtual)."
)

PRAZO_OBSERVAR_S = 25.0
PRAZO_AGIR_S = 60.0
PRAZO_ABRIR_S = 30.0
ESPERA_RAPIDA_S = 4.0
"""No worker, antes de pausar o turno, o bot espera este pouco pelo cartão (o usuário costuma
decidir em segundos): se veio, segue sem pausar."""
PRAZO_CURTO_S = 15.0
ESPERA_CARTAO_S = 90.0
"""Quanto o bot espera, no total, a resposta a um cartão antes de desistir deste turno."""
VALIDADE_CARTAO_S = 600

MAX_PNG_BYTES = 12 * 1024 * 1024
MAX_JANELAS = 40
MAX_ELEMENTOS = 400

PROGRAMAS_BLOQUEADOS = frozenset(
    {
        # UAC, credenciais e tela de bloqueio
        "consent.exe",
        "credentialuibroker.exe",
        "logonui.exe",
        "lockapp.exe",
        # segurança e configurações do Windows
        "sechealthui.exe",
        "securityhealthhost.exe",
        "securityhealthsystray.exe",
        "systemsettings.exe",
        "regedit.exe",
        "mmc.exe",
        "taskmgr.exe",
        # gerenciadores de senha
        "1password.exe",
        "bitwarden.exe",
        "keepass.exe",
        "keepassxc.exe",
        "dashlane.exe",
        "lastpass.exe",
        "nordpass.exe",
        "keeper.exe",
        "keeperpasswordmanager.exe",
        "roboform.exe",
        "enpass.exe",
        "protonpass.exe",
        # terminais (seria um executar_comando no PC do usuário)
        "cmd.exe",
        "powershell.exe",
        "powershell_ise.exe",
        "pwsh.exe",
        "windowsterminal.exe",
        "wt.exe",
        "openconsole.exe",
        "conhost.exe",
        # lançadores e executores de script (Cerca A1): Executar, busca do Iniciar e o resto
        # rodam qualquer comando sem nunca focar um terminal
        "explorer.exe",
        "searchhost.exe",
        "searchapp.exe",
        "searchui.exe",
        "startmenuexperiencehost.exe",
        "shellexperiencehost.exe",
        "wscript.exe",
        "cscript.exe",
        "mshta.exe",
        "rundll32.exe",
        "regsvr32.exe",
        "msiexec.exe",
        "bash.exe",
        "wsl.exe",
        "wslhost.exe",
        "certutil.exe",
        "bitsadmin.exe",
        "schtasks.exe",
        "msbuild.exe",
        "installutil.exe",
        "control.exe",
        # interpretadores e binários que rodam comando, baixam ou instalam (LOLBAS)
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "pyw.exe",
        "node.exe",
        "java.exe",
        "javaw.exe",
        "perl.exe",
        "ruby.exe",
        "php.exe",
        "dotnet.exe",
        "sh.exe",
        "mintty.exe",
        "git-bash.exe",
        "wmic.exe",
        "forfiles.exe",
        "pcalua.exe",
        "msdt.exe",
        "cmstp.exe",
        "hh.exe",
        "odbcconf.exe",
        "regasm.exe",
        "regsvcs.exe",
        "csc.exe",
        "vbc.exe",
        "jsc.exe",
        "presentationhost.exe",
        "scriptrunner.exe",
        "syncappvpublishingserver.exe",
        "ieexec.exe",
        "infdefaultinstall.exe",
        "mavinject.exe",
        "winget.exe",
        "curl.exe",
        "ftp.exe",
        "tftp.exe",
        "reg.exe",
        "sc.exe",
        "net.exe",
        "net1.exe",
        "netsh.exe",
        "bcdedit.exe",
        "vssadmin.exe",
        "wevtutil.exe",
        "takeown.exe",
        "icacls.exe",
        "runas.exe",
        "psexec.exe",
        "psexec64.exe",
        # a própria Sora (o bot não aprova os próprios cartões)
        "sora.exe",
    }
)
"""Espelho da lista da ponte (``app/src-tauri/src/pc/regras.rs``). A ponte é quem confere de
verdade (ela sabe o executável de cada janela); o servidor recusa de novo se o nome aparecer."""

PAPEIS_DE_ESTADO = frozenset({"foco", "senha", "desativado", "marcado", "expandido"})

_MODIFICADORES_SISTEMA = frozenset({"super", "win", "windows", "meta", "cmd", "command", "hyper"})


def tecla_proibida(tecla: str | None) -> bool:
    """Atalhos que abrem outros programas ou trocam para janela não liberada (Cerca A1).

    A ponte recusa de novo (``regras.rs``): tecla Windows, ctrl+Esc (Iniciar), ctrl+shift+Esc
    (Gerenciador de Tarefas), alt+Tab/alt+Esc, ctrl+alt+Delete, as ferramentas do
    desenvolvedor do navegador (F12, ctrl+shift+I/J/C/K), que rodam código na página, e o editor
    e a lista de macros do Office/LibreOffice (alt+F11, alt+F8), que rodam código no programa.
    """
    partes = [p.strip().lower() for p in str(tecla or "").split("+") if p.strip()]
    if not partes:
        return False
    *mods, base = partes
    mods_set = set(mods)
    if mods_set & _MODIFICADORES_SISTEMA or base in _MODIFICADORES_SISTEMA:
        return True
    if base.startswith(("super", "meta", "hyper")) or base in {"menu", "apps"}:
        return True
    ctrl = bool(mods_set & {"ctrl", "control"})
    alt = "alt" in mods_set
    shift = "shift" in mods_set
    if base in {"escape", "esc"} and (ctrl or alt):
        return True
    if base == "tab" and alt:
        return True
    if base in {"delete", "backspace"} and ctrl and alt:
        return True
    if base == "f12":
        return True
    if alt and base in {"f11", "f8"}:
        return True
    return ctrl and shift and base in {"i", "j", "c", "k"}


class _Pausado(Exception):
    pass


class _ProgramaNaoPermitido(Exception):
    def __init__(self, programa: str, titulo: str) -> None:
        super().__init__(programa)
        self.programa = programa
        self.titulo = titulo


def _limpo(texto: Any, limite: int) -> str:
    from app.core.redacao import limpar_texto_sensivel

    return limpar_texto_sensivel(str(texto or ""))[:limite]


def _inteiro(valor: Any, minimo: int = -MAX_COORDENADA, maximo: int = MAX_COORDENADA) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return 0
    return max(minimo, min(maximo, numero))


def normalizar_programa(nome: Any) -> str:
    """``C:\\…\\Notepad.exe`` → ``notepad.exe``."""
    texto = str(nome or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    return texto[:80]


def observacao_do_app(resultado: dict[str, Any]) -> Observacao:
    """Confere e limpa o que a ponte mandou. O app é do usuário, mas nada passa sem conferir."""
    largura = _inteiro(resultado.get("largura"), 1)
    altura = _inteiro(resultado.get("altura"), 1)
    omitida = bool(resultado.get("captura_omitida"))
    if omitida:
        png = _png_preto(largura, altura)  # o que veio no lugar é descartado sem ler
    else:
        try:
            png = base64.b64decode(str(resultado.get("png") or ""), validate=True)
        except (ValueError, TypeError) as erro:
            raise ErroFerramenta("O app de desktop mandou uma captura inválida.") from erro
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_PNG_BYTES:
            raise ErroFerramenta("O app de desktop mandou uma captura inválida.")
    janelas: list[Janela] = []
    for bruta in (resultado.get("janelas") or [])[:MAX_JANELAS]:
        if not isinstance(bruta, dict):
            continue
        programa = normalizar_programa(bruta.get("programa")) or None
        bloqueado = bool(bruta.get("bloqueado")) or programa in PROGRAMAS_BLOQUEADOS
        janelas.append(
            Janela(
                id_nativo=str(bruta.get("id") or "")[:24],
                titulo="(programa bloqueado para bots)"
                if bloqueado
                else _limpo(bruta.get("titulo"), 200),
                x=_inteiro(bruta.get("x")),
                y=_inteiro(bruta.get("y")),
                largura=_inteiro(bruta.get("largura"), 0),
                altura=_inteiro(bruta.get("altura"), 0),
                ativa=bool(bruta.get("ativa")),
                programa=programa,
                outro_monitor=bool(bruta.get("outro_monitor")),
            )
        )
    arvore: list[dict[str, Any]] = []
    for bruto in (resultado.get("arvore") or [])[:MAX_ELEMENTOS]:
        if not isinstance(bruto, dict):
            continue
        estados = [str(e) for e in (bruto.get("estados") or []) if str(e) in PAPEIS_DE_ESTADO][:5]
        elemento: dict[str, Any] = {
            "ref": str(bruto.get("ref") or "")[:12],
            "papel": _limpo(bruto.get("papel"), 40),
            "nome": _limpo(bruto.get("nome"), 120),
        }
        centro = bruto.get("centro")
        if isinstance(centro, list) and len(centro) == 2:
            elemento["centro"] = [_inteiro(centro[0], 0), _inteiro(centro[1], 0)]
        valor = bruto.get("valor")
        if valor not in (None, "") and "senha" not in estados:
            elemento["valor"] = _limpo(valor, 200)
        if estados:
            elemento["estados"] = estados
        arvore.append(elemento)
    if omitida:
        # Programa bloqueado (ou a própria Sora) na frente (Cerca A3): nenhum pixel e nenhum
        # elemento seguem ao modelo, ao Redis ou ao SSE, mesmo que a ponte tenha mandado algo.
        # Fica só uma imagem preta pequena (o tamanho real continua valendo para coordenadas)
        # e o aviso para o bot.
        arvore = [{"ref": "", "papel": "aviso", "nome": CAPTURA_OMITIDA}]
    return Observacao(tela=Tela(png, largura, altura), janelas=janelas, arvore=arvore or None)


@lru_cache(maxsize=8)
def _png_preto(largura: int, altura: int) -> bytes:
    """PNG todo preto, com no máximo 320 px de largura e a mesma proporção da tela."""
    import io

    from PIL import Image

    escala = min(1.0, 320 / max(largura, 1))
    tamanho = (max(1, round(largura * escala)), max(1, round(altura * escala)))
    saida = io.BytesIO()
    Image.new("RGB", tamanho, (0, 0, 0)).save(saida, format="PNG")
    return saida.getvalue()


_MENSAGENS = {
    "nao_autorizado": DESLIGADO_PARA_O_BOT,
    "senha": SENHA,
    "fora_da_tela": "Esse ponto está fora da tela principal do usuário.",
    "so_windows": "O controle do computador só funciona no app de desktop para Windows.",
    "invalido": "O app de desktop recusou o pedido (formato inválido).",
    "janela_sumiu": "Essa janela não existe mais. Observe a tela de novo.",
    "sem_foco": "Não consegui trazer a janela para a frente. Clique nela antes de digitar.",
    "janela_trazida": (
        "Essa janela estava em outro monitor; trouxe para a tela principal. Observe de novo e "
        "repita a ação com as coordenadas da tela nova."
    ),
    "nao_abrivel": NAO_ABRIVEL,
}


def _interromper(valor: dict[str, Any]) -> Any:
    """Pausa o turno do LangGraph até a decisão do cartão (testes trocam esta função)."""
    from langgraph.types import interrupt

    return interrupt(valor)


@dataclass(slots=True)
class ComputadorPcUsuario:
    """O PC do usuário, visto pelo worker. Cada operação é um comando para o app de desktop."""

    canal: CanalPc
    cartoes: Cartoes
    usuario_id: UUID
    agente: AgentePc
    sessao_id: str
    espera_cartao_s: float = ESPERA_CARTAO_S
    intervalo_cartao_s: float = 1.0
    alvo: Alvo = Alvo.PC_USUARIO
    modo_permissao: str = "perguntar"
    """Modo da conversa (Âncora-9). Com ``total`` a primeira ação num programa liberado não pede
    cartão; programa bloqueado, senha, pausa pelo mouse, Parar e borda continuam iguais."""
    ao_aprovar_sozinho: Callable[[str, str], Awaitable[None]] | None = None
    """Avisa o painel Trabalho (modo, resumo) quando o modo dispensou o cartão."""
    contexto: Any = None
    """``ContextoFerramenta`` do turno (o serviço preenche no worker). Com ele, cartão pendente
    pausa o turno em vez de o bot esperar dentro da ferramenta (Vela-12)."""
    feitas: int = 0
    """Ações que já chegaram ao PC nesta chamada de ferramenta (um objeto por chamada)."""
    so_programas: frozenset[str] | None = None
    """Com o juiz dispensado (teclado em editor local, ``revisor/execucao.py``), a ponte só
    aceita estes programas nesta chamada."""

    # ---------- comandos ----------

    async def _preparar(self) -> None:
        if (
            await self.canal.esta_parado(self.usuario_id, self.agente.id)
            and not await self._bloqueio_liberado()
        ):
            raise ErroFerramenta(PARADO)
        if await self.canal.esta_pausado(self.usuario_id, self.agente.id):
            await self._esperar_retomada()
        await self.canal.pegar_vez(self.usuario_id, self.agente)

    async def _enviar(self, operacao: str, dados: dict[str, Any], prazo_s: float) -> dict[str, Any]:
        resposta = await self.canal.enviar(
            self.usuario_id, self.sessao_id, self.agente, operacao, dados, prazo_s
        )
        assert resposta is not None
        if resposta.get("ok") is True:
            resultado = resposta.get("resultado")
            return resultado if isinstance(resultado, dict) else {}
        erro = resposta.get("erro") if isinstance(resposta.get("erro"), dict) else {}
        codigo = str(erro.get("codigo") or "falha")
        if codigo == "pausado":
            await self.canal.marcar_pausado(self.usuario_id, self.agente.id)
            raise _Pausado()
        if codigo == "parado":
            await self.canal.marcar_parado(self.usuario_id, self.agente.id)
            raise ErroFerramenta(PARADO)
        if codigo == "programa_nao_permitido":
            programa = normalizar_programa(erro.get("programa"))
            if not programa:
                raise ErroFerramenta("O app de desktop não disse qual é o programa.")
            raise _ProgramaNaoPermitido(programa, str(erro.get("titulo") or ""))
        if codigo == "programa_bloqueado":
            programa = normalizar_programa(erro.get("programa")) or "esse programa"
            raise ErroFerramenta(self._bloqueado(programa))
        if codigo == "processo_bloqueado":
            await self._parar_por_bloqueio(normalizar_programa(erro.get("programa")))
        if codigo == "nao_instalado":
            rotulo = _limpo(erro.get("titulo"), 40) or "Esse programa"
            raise ErroFerramenta(NAO_INSTALADO.format(programa=rotulo))
        if codigo == "em_uso":
            nome = _limpo(erro.get("por"), 60) or "outro bot"
            raise ErroFerramenta(f"O PC está em uso por {nome}. Tente de novo quando ele terminar.")
        if codigo in _MENSAGENS:
            raise ErroFerramenta(_MENSAGENS[codigo])
        detalhe = _limpo(erro.get("mensagem"), 200)
        raise ErroFerramenta(
            "A ação falhou no computador do usuário" + (f": {detalhe}" if detalhe else ".")
        )

    @staticmethod
    def _bloqueado(programa: str) -> str:
        return (
            f"{programa} é bloqueado para bots (senhas, segurança do Windows, UAC, terminal ou a "
            "própria Sora). Peça ao usuário para fazer essa parte ele mesmo."
        )

    # ---------- cartões ----------

    async def _cartao(self, assunto: str, acao: dict[str, Any], motivo: str) -> str:
        """Abre (ou reaproveita) o cartão deste assunto e espera a decisão por um tempo.
        Devolve ``permitida``, ``negada`` ou ``pendente``."""
        u, a = self.usuario_id, self.agente.id
        # Esperando o usuário, o bot não mexe no PC: solta a vez **antes** de o cartão aparecer,
        # para que a decisão possa vir de qualquer sessão (com a vez presa, só o app de desktop
        # decide; Cerca A2). Quem segue depois pega a vez de novo.
        await self.canal.soltar_vez(u, a)
        guardado = await self.canal.cartao(u, a, assunto)
        status: str | None = None
        aprovacao_id: UUID | None = None
        desde = time.time()
        if guardado:
            try:
                aprovacao_id = UUID(str(guardado.get("id")))
                desde = float(guardado.get("desde") or desde)
            except (TypeError, ValueError):
                aprovacao_id = None
            if aprovacao_id is not None:
                status = await self.cartoes.status(u, aprovacao_id)
        if status == "expirada" and guardado and guardado.get("vinculado"):
            # o turno pausou neste cartão e ele venceu sem resposta: vale como recusa
            await self.canal.esquecer_cartao(u, a, assunto)
            return "negada"
        if aprovacao_id is None or status in (None, "expirada"):
            aprovacao_id = await self.cartoes.abrir(u, a, acao, motivo)
            desde = time.time()
            await self.canal.guardar_cartao(u, a, assunto, aprovacao_id, VALIDADE_CARTAO_S)
            status = "pendente"
        if status == "pendente" and self.contexto is not None:
            return await self._pausar_o_turno(assunto, aprovacao_id)
        while status == "pendente" and time.time() < desde + self.espera_cartao_s:
            await asyncio.sleep(self.intervalo_cartao_s)
            status = await self.cartoes.status(u, aprovacao_id)
        if status == "permitida":
            await self.canal.esquecer_cartao(u, a, assunto)  # decisão usada
            return "permitida"
        if status == "negada":
            return "negada"
        return "pendente"

    async def _pausar_o_turno(self, assunto: str, aprovacao_id: UUID) -> str:
        """No worker: espera um pouco; ainda pendente, liga o cartão ao turno e pausa (Vela-12).

        Só pausa se nada foi feito nesta chamada (a retomada roda a ferramenta de novo, do
        começo). Senão devolve ``fila``: quem chamou avisa o bot e a próxima chamada pausa."""
        u, a = self.usuario_id, self.agente.id
        limite = time.time() + ESPERA_RAPIDA_S
        status = await self.cartoes.status(u, aprovacao_id)
        while status == "pendente" and time.time() < limite:
            await asyncio.sleep(min(self.intervalo_cartao_s, 0.5))
            status = await self.cartoes.status(u, aprovacao_id)
        if status != "pendente":
            if status == "permitida":
                await self.canal.esquecer_cartao(u, a, assunto)
                return "permitida"
            return "negada" if status == "negada" else "pendente"
        if self.feitas:
            return "fila"
        ctx = self.contexto
        expira_em = await self.cartoes.vincular(
            u,
            aprovacao_id,
            conversa_id=ctx.conversa_id,
            etapa_id=ctx.etapa_id,
            grupo_id=ctx.canal_id,
        )
        if not expira_em:  # decidido entre a última leitura e agora
            status = await self.cartoes.status(u, aprovacao_id)
            if status == "permitida":
                await self.canal.esquecer_cartao(u, a, assunto)
                return "permitida"
            return "negada" if status in ("negada", "expirada") else "pendente"
        await self.canal.guardar_cartao(
            u, a, assunto, aprovacao_id, VALIDADE_CARTAO_S, vinculado=True
        )
        if expira_em is not True:
            from app.ferramentas.criar_agente import _agendar_expiracao

            await _agendar_expiracao(aprovacao_id, expira_em)
        decisao = str(_interromper({"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id)}))
        # A retomada roda a ferramenta de novo e o cartão já vem decidido do banco; este valor
        # só chega aqui quando o LangGraph devolve a decisão na mesma execução.
        if decisao in ("negar", "negada", "expirada"):
            return "negada"
        await self.canal.esquecer_cartao(u, a, assunto)
        return "permitida"

    async def _pedir_programa(self, programa: str, titulo: str) -> None:
        if programa in PROGRAMAS_BLOQUEADOS:
            raise ErroFerramenta(self._bloqueado(programa))
        titulo_seguro = _limpo(titulo, 80)
        onde = f"{programa} (“{titulo_seguro}”)" if titulo_seguro else programa
        nome = self.agente.nome
        if self.modo_permissao == "total":
            from app.revisor.decisoes import aprova_sozinho

            pedido = {
                "tipo": "pc_programa",
                "ferramenta": FERRAMENTA_PROGRAMA,
                "argumentos": {"programa": programa},
                "condicao": {"programa": programa},
            }
            if aprova_sozinho("total", pedido):
                await self.canal.permitir_uma_vez(self.usuario_id, self.agente.id, programa)
                if self.ao_aprovar_sozinho is not None:
                    try:
                        await self.ao_aprovar_sozinho("total", f"usar {onde} no seu computador")
                    except Exception:  # o aviso é só de leitura: nunca derruba a ação
                        pass
                return
        acao = {
            "tipo": "pc_programa",
            "ferramenta": FERRAMENTA_PROGRAMA,
            "argumentos": {"programa": programa},
            "condicao": {"programa": programa},
            "titulo": "Usar um programa do seu computador",
            "resumo": (
                f"{nome} quer usar {onde} no seu computador. É a primeira ação dele nesse "
                "programa. “Sempre permitir” vale só para este programa e este bot."
            ),
        }
        decisao = await self._cartao(
            f"programa:{programa}", acao, f"Primeira ação em {programa} no seu computador."
        )
        if decisao == "permitida":
            await self.canal.permitir_uma_vez(self.usuario_id, self.agente.id, programa)
            return
        if decisao == "negada":
            raise ErroFerramenta(
                f"O usuário não deixou usar {programa}. Não tente de novo; siga sem esse programa "
                "e avise o usuário."
            )
        if decisao == "fila":
            raise ErroFerramenta(CARTAO_NA_FILA.format(programa=programa))
        raise ErroFerramenta(PROGRAMA_ESPERANDO.format(programa=programa))

    async def _parar_por_bloqueio(self, programa: str) -> None:
        """A ponte viu nascer um programa bloqueado (terminal, script…) durante a ação: parar,
        abrir cartão e nunca seguir. Permitir no cartão solta o bot; Recusar o mantém parado."""
        programa = programa or "um programa bloqueado"
        u, a = self.usuario_id, self.agente.id
        await self.canal.marcar_bloqueio(u, a)
        acao = {
            "tipo": "pc_bloqueio",
            "titulo": "Um bot abriu um programa bloqueado",
            "resumo": (
                f"Durante uma ação de {self.agente.nome} no seu computador, {programa} abriu. "
                "Programas assim (terminal, scripts, registro) são bloqueados para bots: fechei "
                f"o programa e parei o controle. “Permitir uma vez”: {self.agente.nome} pode "
                "voltar a usar o computador. “Recusar”: continua parado."
            ),
        }
        try:
            aprovacao_id = await self.cartoes.abrir(
                u, a, acao, f"{programa} abriu durante a ação do bot."
            )
            await self.canal.guardar_cartao(u, a, "bloqueio", aprovacao_id, VALIDADE_CARTAO_S)
        finally:
            await self.encerrar()
        raise ErroFerramenta(BLOQUEIO.format(programa=programa))

    async def _bloqueio_liberado(self) -> bool:
        """Parado por programa bloqueado e o usuário permitiu no cartão: volta a valer."""
        u, a = self.usuario_id, self.agente.id
        guardado = await self.canal.cartao(u, a, "bloqueio")
        if not guardado:
            return False
        try:
            aprovacao_id = UUID(str(guardado.get("id")))
        except (TypeError, ValueError):
            return False
        if await self.cartoes.status(u, aprovacao_id) != "permitida":
            return False
        await self.canal.esquecer_cartao(u, a, "bloqueio")
        await self.canal.limpar_parado(u, a)
        return True

    async def _esperar_retomada(self) -> None:
        """Pausado: cartão para retomar. Volta normalmente só se o usuário mandou retomar."""
        nome = self.agente.nome
        acao = {
            "tipo": "pc_retomar",
            "titulo": "Retomar o controle do computador?",
            "resumo": (
                f"Você mexeu no mouse ou no teclado e {nome} pausou. “Permitir uma vez”: {nome} "
                "volta a usar o seu computador. “Recusar”: ele para."
            ),
        }
        decisao = await self._cartao("retomar", acao, "Pausado porque você usou o computador.")
        if decisao == "permitida":
            await self.canal.limpar_pausa(self.usuario_id, self.agente.id)
            await self.canal.pegar_vez(self.usuario_id, self.agente)
            await self._enviar("retomar", {}, PRAZO_CURTO_S)
            return
        if decisao == "negada":
            await self.canal.marcar_parado(self.usuario_id, self.agente.id)
            await self.encerrar()
            raise ErroFerramenta(RECUSOU_RETOMAR)
        if decisao == "fila":
            raise ErroFerramenta(PAUSOU_NO_MEIO)
        raise ErroFerramenta(PAUSADO_ESPERANDO)

    async def encerrar(self) -> None:
        """Avisa a ponte para apagar a borda e soltar este bot (sem esperar resposta)."""
        await self.canal.enviar(
            self.usuario_id,
            self.sessao_id,
            self.agente,
            "encerrar",
            {},
            PRAZO_CURTO_S,
            esperar=False,
        )

    # ---------- interface Computador ----------

    async def observar(self) -> Observacao:
        return await self._observar(estavel=False)

    async def observar_estavel(self) -> Observacao:
        """Conferência depois de agir: a ponte espera a tela parar de mudar e manda uma captura
        só (antes eram até três observações completas, com ida e volta cada uma)."""
        return await self._observar(estavel=True)

    async def _observar(self, *, estavel: bool) -> Observacao:
        await self._preparar()
        dados = {"estavel": True} if estavel else {}
        try:
            resultado = await self._enviar("observar", dados, PRAZO_OBSERVAR_S)
        except _Pausado:
            await self._esperar_retomada()
            resultado = await self._enviar("observar", dados, PRAZO_OBSERVAR_S)
        return observacao_do_app(resultado)

    @staticmethod
    def acao_para_app(resolvida: AcaoResolvida) -> dict[str, Any]:
        acao = resolvida.acao
        dados: dict[str, Any] = {"tipo": acao.tipo}
        if resolvida.ponto is not None:
            dados["x"], dados["y"] = resolvida.ponto
        if acao.ate_x is not None and acao.ate_y is not None:
            dados["ate_x"], dados["ate_y"] = acao.ate_x, acao.ate_y
        if acao.tipo == "digitar":
            dados["texto"] = acao.texto or ""
        if acao.tipo == "tecla":
            dados["tecla"] = resolvida.tecla
        if acao.tipo == "rolar":
            dados["direcao"], dados["quantidade"] = acao.direcao, acao.quantidade
        if resolvida.janela is not None:
            dados["janela"] = resolvida.janela.id_nativo
        return dados

    async def agir(self, acao: AcaoResolvida) -> None:
        if acao.acao.tipo == "abrir":
            raise ErroFerramenta(ABRIR)
        if acao.acao.tipo == "digitar" and parece_senha(acao.acao.texto or ""):
            raise ErroFerramenta(SENHA)
        if acao.acao.tipo == "tecla" and tecla_proibida(acao.tecla or acao.acao.tecla):
            raise ErroFerramenta(TECLA_PROIBIDA)
        await self._preparar()
        dados = self.acao_para_app(acao)
        for tentativa in range(2):
            permitidos = await self._permitidos()
            try:
                await self._enviar(
                    "agir",
                    {"acao": dados, "programas_permitidos": sorted(permitidos)},
                    PRAZO_AGIR_S,
                )
                self.feitas += 1
                return
            except _Pausado:
                if self.contexto is not None:
                    # a ação pode ter ficado pela metade: nada de pausar o turno aqui (a retomada
                    # repetiria a chamada inteira); a próxima chamada espera o cartão
                    self.feitas += 1
                    raise ErroFerramenta(PAUSOU_NO_MEIO) from None
                await self._esperar_retomada()
                raise ErroFerramenta(RETOMADO) from None
            except _ProgramaNaoPermitido as pedido:
                if tentativa:
                    raise ErroFerramenta(
                        f"{pedido.programa} ainda não está liberado. Observe a tela de novo."
                    ) from None
                await self._pedir_programa(pedido.programa, pedido.titulo)
                # a vez ficou solta enquanto o usuário decidia (``_cartao``): pegar de novo
                await self.canal.pegar_vez(self.usuario_id, self.agente)

    async def _permitidos(self) -> set[str]:
        permitidos = await self.cartoes.programas_sempre(self.usuario_id, self.agente.id)
        permitidos |= await self.canal.programas_uma_vez(self.usuario_id, self.agente.id)
        if self.so_programas is not None:
            permitidos &= self.so_programas
        return permitidos

    async def abrir_programa(self, nome: str) -> dict[str, Any]:
        """Abre pelo nome um programa da lista fechada (a ponte confere de novo). A primeira vez
        em cada programa passa pelo mesmo cartão de ``agir``."""
        await self._preparar()
        for tentativa in range(2):
            permitidos = await self._permitidos()
            try:
                resultado = await self._enviar(
                    "abrir_programa",
                    {"programa": str(nome)[:60], "programas_permitidos": sorted(permitidos)},
                    PRAZO_ABRIR_S,
                )
                self.feitas += 1
                return resultado
            except _Pausado:
                if self.contexto is not None:
                    self.feitas += 1
                    raise ErroFerramenta(PAUSOU_NO_MEIO) from None
                await self._esperar_retomada()
                raise ErroFerramenta(RETOMADO) from None
            except _ProgramaNaoPermitido as pedido:
                if tentativa:
                    raise ErroFerramenta(
                        f"{pedido.programa} ainda não está liberado. Tente de novo."
                    ) from None
                await self._pedir_programa(pedido.programa, pedido.titulo)
                await self.canal.pegar_vez(self.usuario_id, self.agente)
        raise ErroFerramenta("Não consegui abrir o programa.")

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        raise ErroFerramenta(ARQUIVOS)

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        raise ErroFerramenta(ARQUIVOS)

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        raise ErroFerramenta(ARQUIVOS)


@dataclass(slots=True)
class ProvedorPcUsuario:
    """Entrega o PC do usuário se o app de desktop estiver conectado e o bot ligado nele."""

    redis: Any = None
    """``None`` = o Redis dos eventos do processo (o mesmo da API)."""
    cartoes: Cartoes | None = None
    espera_cartao_s: float = ESPERA_CARTAO_S

    def canal(self) -> CanalPc:
        if self.redis is None:
            from app.ferramentas.ambiente import redis_dos_eventos

            return CanalPc(redis_dos_eventos())
        return CanalPc(self.redis)

    async def obter(self, usuario_id: UUID, agente_id: UUID) -> ComputadorPcUsuario:
        from redis.exceptions import RedisError

        canal = self.canal()
        try:
            sessao = await canal.sessao(usuario_id)
        except (RedisError, OSError) as erro:
            raise SemApp(RECUSA) from erro
        if sessao is None:
            raise SemApp(RECUSA)
        if str(agente_id) not in (sessao.get("autorizados") or []):
            raise SemApp(DESLIGADO_PARA_O_BOT)
        cartoes = self.cartoes or CartoesBanco()
        agente = await cartoes.agente(usuario_id, agente_id)
        if agente is None:
            raise ErroFerramenta("Bot não encontrado.")
        return ComputadorPcUsuario(
            canal=canal,
            cartoes=cartoes,
            usuario_id=usuario_id,
            agente=agente,
            sessao_id=str(sessao["sessao_id"]),
            espera_cartao_s=self.espera_cartao_s,
        )

    async def desligar(self, agente_id: UUID) -> bool:
        """O PC do usuário não "desliga": a vez do bot vence sozinha (``VEZ_S``) ou pelo Parar."""
        return False

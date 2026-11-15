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
- nunca digita senha nem mexe em campo de senha; programas de senha, segurança do Windows, UAC,
  terminais e a própria Sora são bloqueados; o texto digitado nunca vai para o rastro;
- nada de arquivos do PC por aqui (só tela, mouse e teclado) e nunca em rotina sem supervisão
  (o serviço recusa antes).
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
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
    "Peça ao usuário para abrir o app de desktop, ou use o computador virtual (alvo virtual)."
)
DESLIGADO_PARA_O_BOT = (
    "O usuário não ligou o controle do computador para este bot. Ele liga em Configurações → "
    "Computador, no app de desktop. Até lá, use o computador virtual (alvo virtual)."
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
    "No computador do usuário eu não abro programas por comando. Use ctrl+Escape (menu Iniciar), "
    "digite o nome do programa e Enter, ou peça ao usuário para abrir."
)
ARQUIVOS = (
    "No computador do usuário não leio nem gravo arquivos direto: só tela, mouse e teclado. "
    "Para arquivos, use o computador virtual (alvo virtual)."
)

PRAZO_OBSERVAR_S = 25.0
PRAZO_AGIR_S = 60.0
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
        # a própria Sora (o bot não aprova os próprios cartões)
        "sora.exe",
    }
)
"""Espelho da lista da ponte (``app/src-tauri/src/pc/regras.rs``). A ponte é quem confere de
verdade (ela sabe o executável de cada janela); o servidor recusa de novo se o nome aparecer."""

PAPEIS_DE_ESTADO = frozenset({"foco", "senha", "desativado", "marcado", "expandido"})


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
    try:
        png = base64.b64decode(str(resultado.get("png") or ""), validate=True)
    except (ValueError, TypeError) as erro:
        raise ErroFerramenta("O app de desktop mandou uma captura inválida.") from erro
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_PNG_BYTES:
        raise ErroFerramenta("O app de desktop mandou uma captura inválida.")
    largura = _inteiro(resultado.get("largura"), 1)
    altura = _inteiro(resultado.get("altura"), 1)
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
    return Observacao(tela=Tela(png, largura, altura), janelas=janelas, arvore=arvore or None)


_MENSAGENS = {
    "nao_autorizado": DESLIGADO_PARA_O_BOT,
    "senha": SENHA,
    "fora_da_tela": "Esse ponto está fora da tela principal do usuário.",
    "so_windows": "O controle do computador só funciona no app de desktop para Windows.",
    "invalido": "O app de desktop recusou o pedido (formato inválido).",
    "janela_sumiu": "Essa janela não existe mais. Observe a tela de novo.",
    "sem_foco": "Não consegui trazer a janela para a frente. Clique nela antes de digitar.",
}


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

    # ---------- comandos ----------

    async def _preparar(self) -> None:
        if await self.canal.esta_parado(self.usuario_id, self.agente.id):
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
        if aprovacao_id is None or status in (None, "expirada"):
            aprovacao_id = await self.cartoes.abrir(u, a, acao, motivo)
            desde = time.time()
            await self.canal.guardar_cartao(u, a, assunto, aprovacao_id, VALIDADE_CARTAO_S)
            status = "pendente"
        while status == "pendente" and time.time() < desde + self.espera_cartao_s:
            await asyncio.sleep(self.intervalo_cartao_s)
            status = await self.cartoes.status(u, aprovacao_id)
        if status == "permitida":
            await self.canal.esquecer_cartao(u, a, assunto)  # decisão usada
            return "permitida"
        if status == "negada":
            return "negada"
        return "pendente"

    async def _pedir_programa(self, programa: str, titulo: str) -> None:
        if programa in PROGRAMAS_BLOQUEADOS:
            raise ErroFerramenta(self._bloqueado(programa))
        titulo_seguro = _limpo(titulo, 80)
        onde = f"{programa} (“{titulo_seguro}”)" if titulo_seguro else programa
        nome = self.agente.nome
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
        raise ErroFerramenta(PROGRAMA_ESPERANDO.format(programa=programa))

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
        await self._preparar()
        try:
            resultado = await self._enviar("observar", {}, PRAZO_OBSERVAR_S)
        except _Pausado:
            await self._esperar_retomada()
            resultado = await self._enviar("observar", {}, PRAZO_OBSERVAR_S)
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
        await self._preparar()
        dados = self.acao_para_app(acao)
        for tentativa in range(2):
            permitidos = await self.cartoes.programas_sempre(self.usuario_id, self.agente.id)
            permitidos |= await self.canal.programas_uma_vez(self.usuario_id, self.agente.id)
            try:
                await self._enviar(
                    "agir",
                    {"acao": dados, "programas_permitidos": sorted(permitidos)},
                    PRAZO_AGIR_S,
                )
                return
            except _Pausado:
                await self._esperar_retomada()
                raise ErroFerramenta(RETOMADO) from None
            except _ProgramaNaoPermitido as pedido:
                if tentativa:
                    raise ErroFerramenta(
                        f"{pedido.programa} ainda não está liberado. Observe a tela de novo."
                    ) from None
                await self._pedir_programa(pedido.programa, pedido.titulo)

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

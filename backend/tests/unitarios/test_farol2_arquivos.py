"""Farol-2, item 3: o arquivo do computador vira anexo (a área de arquivos some ao desligar)."""

from __future__ import annotations

from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest

from app.computador.interface import Alvo, ArquivoArea, Janela, Observacao, Tela
from app.computador.pc_usuario import ProvedorPcUsuario
from app.computador.servico import MAX_ENTREGA_BYTES, ServicoComputador
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.revisor.politica import Politica, pode_sem_supervisao, politica_da_ferramenta


class _Computador:
    alvo = Alvo.VIRTUAL

    def __init__(self) -> None:
        self.arquivos: dict[str, bytes] = {}

    async def observar(self) -> Observacao:
        return Observacao(tela=Tela(b"x", 1, 1), janelas=[Janela("0x1", "a", 0, 0, 1, 1)])

    async def agir(self, acao) -> None:
        return None

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        return []

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        dados = self.arquivos[caminho]
        return dados[: limite + 1]

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        self.arquivos[caminho] = dados


class _Provedor:
    def __init__(self) -> None:
        self.computador = _Computador()

    async def obter(self, usuario_id, agente_id) -> _Computador:
        return self.computador

    async def desligar(self, agente_id) -> bool:
        return True


def _servico(guardados: list[tuple[str, bytes]]) -> tuple[ServicoComputador, _Provedor]:
    async def publicar(_e, _u) -> None:
        return None

    async def guardar(_ctx: ContextoFerramenta, nome: str, dados: bytes) -> UUID:
        guardados.append((nome, dados))
        return uuid4()

    provedor = _Provedor()
    servico = ServicoComputador(
        provedores={Alvo.VIRTUAL: provedor, Alvo.PC_USUARIO: ProvedorPcUsuario()},
        redis=fakeredis.aioredis.FakeRedis(),
        publicar=publicar,
        guardar_anexo=guardar,
    )
    return servico, provedor


def _ctx(**extra) -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), **extra)


async def test_entregar_leva_o_arquivo_para_a_conversa_como_anexo() -> None:
    guardados: list[tuple[str, bytes]] = []
    servico, provedor = _servico(guardados)
    provedor.computador.arquivos["relatorios/maio.csv"] = "café;5\n".encode()
    texto = await servico.entregar(_ctx(), "relatorios/maio.csv")
    assert guardados == [("maio.csv", "café;5\n".encode())]
    assert "anexo_id" in texto and "não some" in texto


async def test_entregar_recusa_vazio_grande_e_rotina_sem_supervisao() -> None:
    guardados: list[tuple[str, bytes]] = []
    servico, provedor = _servico(guardados)
    provedor.computador.arquivos["vazio.txt"] = b""
    provedor.computador.arquivos["grande.bin"] = b"0" * (MAX_ENTREGA_BYTES + 1)
    with pytest.raises(ErroFerramenta, match="vazio"):
        await servico.entregar(_ctx(), "vazio.txt")
    with pytest.raises(ErroFerramenta, match="passa de 10 MB"):
        await servico.entregar(_ctx(), "grande.bin")
    with pytest.raises(ErroFerramenta, match="rotinas sem supervisão"):
        await servico.entregar(_ctx(sem_supervisao=True), "vazio.txt")
    assert guardados == []


def test_ferramenta_registrada_com_politica_e_rotulo() -> None:
    from app.computador.ferramentas import NOMES
    from app.ferramentas.registro import ESQUEMAS
    from app.ferramentas.rotulos import rotulo_do_passo

    assert "computador_entregar_arquivo" in NOMES and "computador_entregar_arquivo" in ESQUEMAS
    assert politica_da_ferramenta("computador_entregar_arquivo") is Politica.LIVRE
    assert not pode_sem_supervisao("computador_entregar_arquivo")
    assert "x.csv" in rotulo_do_passo("computador_entregar_arquivo", {"caminho": "x.csv"})

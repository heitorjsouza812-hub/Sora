"""Memória explícita dos agentes (fase 2): ``lembrar``, ``buscar_memoria`` e
``esquecer_memoria`` sobre a tabela ``memorias``.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``packages/memory`` (armazém com
revisões e exportação), ``adapters/src/memory-tools.ts`` (``remember``, ``save_memory``,
``recall_memory``, ``forget_memory``) e ``memory-context.ts`` (no máximo 5 memórias injetadas,
cercadas como dado).

O armazém fica atrás de ``ArmazemMemorias``: ``ArmazemMemoriasSQL`` no PostgreSQL (busca
semântica pelo pgvector quando houver ``Vetorizador``; senão, palavras) e
``ArmazemMemoriasEmMemoria`` para testes e desenvolvimento.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.redacao import limpar_texto_sensivel
from app.ferramentas.base import ErroFerramenta
from app.ferramentas.historico import normalizar, palavras_da_consulta
from app.memoria.compactacao import MAX_MEMORIAS_RECUPERADAS, formatar_memorias

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_CONTEUDO = 500
DIMENSOES = 768


class Lembrar(BaseModel):
    """Guarda um fato durável (preferência, decisão, contexto que se repete)."""

    conteudo: str = Field(min_length=1, max_length=MAX_CONTEUDO)


class BuscarMemoria(BaseModel):
    """Busca nas memórias guardadas os fatos ligados à consulta."""

    consulta: str = Field(min_length=1, max_length=400)


class EsquecerMemoria(BaseModel):
    """Apaga uma memória pelo id (pede aprovação ao usuário)."""

    memoria_id: UUID


@dataclass(slots=True)
class RegistroMemoria:
    id: UUID
    usuario_id: UUID
    agente_id: UUID | None
    conteudo: str
    tipo: str = "perfil"
    origem: str = "explicita"
    travada: bool = True
    criada_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    apagada_em: datetime | None = None


class Vetorizador(Protocol):
    """Gera o embedding (768 dimensões) de um texto, com a chave do usuário."""

    async def vetorizar(self, texto: str) -> list[float]: ...


class ArmazemMemorias(Protocol):
    async def salvar(
        self, registro: RegistroMemoria, vetor: list[float] | None = None
    ) -> RegistroMemoria: ...

    async def buscar(
        self,
        usuario_id: UUID,
        agente_id: UUID | None,
        consulta: str,
        limite: int,
        vetor: list[float] | None = None,
    ) -> list[RegistroMemoria]: ...

    async def apagar(self, usuario_id: UUID, memoria_id: UUID) -> bool: ...

    async def listar(self, usuario_id: UUID, agente_id: UUID | None) -> list[RegistroMemoria]: ...


def validar_conteudo(conteudo: str) -> str:
    """Normaliza espaços e recusa o que parece senha, chave ou token."""
    texto = " ".join(conteudo.split())
    if not texto:
        raise ErroFerramenta("A memória está vazia.")
    if len(texto) > MAX_CONTEUDO:
        raise ErroFerramenta(f"A memória passa de {MAX_CONTEUDO} caracteres. Resuma o fato.")
    if limpar_texto_sensivel(texto) != texto:
        raise ErroFerramenta("Não guardo senhas, chaves ou tokens na memória.")
    return texto


def _pontos(registro: RegistroMemoria, palavras: list[str]) -> int:
    texto = normalizar(registro.conteudo)
    return sum(1 for p in palavras if p in texto)


class ArmazemMemoriasEmMemoria:
    """Armazém em memória (testes e desenvolvimento)."""

    def __init__(self) -> None:
        self.registros: dict[UUID, RegistroMemoria] = {}

    async def salvar(
        self, registro: RegistroMemoria, vetor: list[float] | None = None
    ) -> RegistroMemoria:
        self.registros[registro.id] = registro
        return registro

    def _visiveis(self, usuario_id: UUID, agente_id: UUID | None) -> list[RegistroMemoria]:
        return [
            r
            for r in self.registros.values()
            if r.usuario_id == usuario_id
            and r.apagada_em is None
            and (r.agente_id is None or r.agente_id == agente_id)
        ]

    async def buscar(
        self,
        usuario_id: UUID,
        agente_id: UUID | None,
        consulta: str,
        limite: int,
        vetor: list[float] | None = None,
    ) -> list[RegistroMemoria]:
        palavras = palavras_da_consulta(consulta)
        pontuados = [(_pontos(r, palavras), r) for r in self._visiveis(usuario_id, agente_id)]
        pontuados = [par for par in pontuados if par[0] > 0]
        pontuados.sort(key=lambda par: (par[0], par[1].criada_em), reverse=True)
        return [r for _, r in pontuados[:limite]]

    async def apagar(self, usuario_id: UUID, memoria_id: UUID) -> bool:
        registro = self.registros.get(memoria_id)
        if registro is None or registro.usuario_id != usuario_id or registro.apagada_em:
            return False
        registro.apagada_em = datetime.now(UTC)
        return True

    async def listar(self, usuario_id: UUID, agente_id: UUID | None) -> list[RegistroMemoria]:
        return sorted(
            self._visiveis(usuario_id, agente_id), key=lambda r: r.criada_em, reverse=True
        )


class ArmazemMemoriasSQL:
    """Armazém sobre ``memorias`` (só do dono; apagar é ``apagada_em``, nunca DELETE)."""

    def __init__(self, sessao: AsyncSession) -> None:
        self.sessao = sessao

    @staticmethod
    def _para_registro(linha: object) -> RegistroMemoria:
        return RegistroMemoria(
            id=linha.id,  # type: ignore[attr-defined]
            usuario_id=linha.usuario_id,  # type: ignore[attr-defined]
            agente_id=linha.agente_id,  # type: ignore[attr-defined]
            conteudo=linha.conteudo,  # type: ignore[attr-defined]
            tipo=str(getattr(linha.tipo, "value", linha.tipo)),  # type: ignore[attr-defined]
            origem=str(getattr(linha.origem, "value", linha.origem)),  # type: ignore[attr-defined]
            travada=linha.travada,  # type: ignore[attr-defined]
            criada_em=linha.criada_em,  # type: ignore[attr-defined]
            apagada_em=linha.apagada_em,  # type: ignore[attr-defined]
        )

    async def salvar(
        self, registro: RegistroMemoria, vetor: list[float] | None = None
    ) -> RegistroMemoria:
        from app.modelos.enumeracoes import OrigemMemoria, TipoMemoria
        from app.modelos.tabelas import Memoria

        linha = Memoria(
            id=registro.id,
            usuario_id=registro.usuario_id,
            agente_id=registro.agente_id,
            tipo=TipoMemoria(registro.tipo),
            conteudo=registro.conteudo,
            origem=OrigemMemoria(registro.origem),
            travada=registro.travada,
            embedding=_vetor_texto(vetor) if vetor else None,
        )
        self.sessao.add(linha)
        await self.sessao.flush()
        return registro

    def _filtro(self, usuario_id: UUID, agente_id: UUID | None):  # type: ignore[no-untyped-def]
        from sqlalchemy import or_

        from app.modelos.tabelas import Memoria

        return (
            Memoria.usuario_id == usuario_id,
            Memoria.apagada_em.is_(None),
            or_(Memoria.agente_id.is_(None), Memoria.agente_id == agente_id),
        )

    async def buscar(
        self,
        usuario_id: UUID,
        agente_id: UUID | None,
        consulta: str,
        limite: int,
        vetor: list[float] | None = None,
    ) -> list[RegistroMemoria]:
        from sqlalchemy import and_, literal_column, or_, select

        from app.modelos.tabelas import Memoria

        base = select(Memoria).where(*self._filtro(usuario_id, agente_id))
        if vetor:
            distancia = literal_column("memorias.embedding").op("<=>")(
                literal_column(f"'{_vetor_texto(vetor)}'::vector")
            )
            consulta_sql = base.where(Memoria.embedding.is_not(None)).order_by(distancia)
        else:
            palavras = [p for p in palavras_da_consulta(consulta) if len(p) > 2][:8]
            if not palavras:
                return []
            condicoes = [
                Memoria.conteudo.ilike(f"%{_escapar_like(p)}%", escape="\\") for p in palavras
            ]
            consulta_sql = base.where(or_(*condicoes) if len(condicoes) > 1 else and_(*condicoes))
            consulta_sql = consulta_sql.order_by(Memoria.criada_em.desc())
        linhas = (await self.sessao.execute(consulta_sql.limit(limite))).scalars().all()
        return [self._para_registro(linha) for linha in linhas]

    async def apagar(self, usuario_id: UUID, memoria_id: UUID) -> bool:
        from sqlalchemy import update

        from app.modelos.tabelas import Memoria

        resultado = await self.sessao.execute(
            update(Memoria)
            .where(
                Memoria.id == memoria_id,
                Memoria.usuario_id == usuario_id,
                Memoria.apagada_em.is_(None),
            )
            .values(apagada_em=datetime.now(UTC))
        )
        return bool(resultado.rowcount)  # type: ignore[attr-defined]

    async def listar(self, usuario_id: UUID, agente_id: UUID | None) -> list[RegistroMemoria]:
        from sqlalchemy import select

        from app.modelos.tabelas import Memoria

        linhas = (
            (
                await self.sessao.execute(
                    select(Memoria)
                    .where(*self._filtro(usuario_id, agente_id))
                    .order_by(Memoria.criada_em.desc())
                )
            )
            .scalars()
            .all()
        )
        return [self._para_registro(linha) for linha in linhas]


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _vetor_texto(vetor: Sequence[float]) -> str:
    if len(vetor) != DIMENSOES:
        raise ValueError(f"O embedding precisa ter {DIMENSOES} dimensões.")
    return "[" + ",".join(f"{float(v):.7g}" for v in vetor) + "]"


class ServicoMemoria:
    """O que as ferramentas e o worker usam."""

    def __init__(self, armazem: ArmazemMemorias, vetorizador: Vetorizador | None = None) -> None:
        self.armazem = armazem
        self.vetorizador = vetorizador

    async def _vetor(self, texto: str) -> list[float] | None:
        if self.vetorizador is None:
            return None
        try:
            return await self.vetorizador.vetorizar(texto)
        except Exception:
            return None

    async def lembrar(
        self, usuario_id: UUID, agente_id: UUID | None, conteudo: str, *, explicita: bool = True
    ) -> RegistroMemoria:
        texto = validar_conteudo(conteudo)
        existentes = await self.armazem.listar(usuario_id, agente_id)
        for registro in existentes:
            if normalizar(registro.conteudo) == normalizar(texto):
                return registro
        registro = RegistroMemoria(
            id=uuid4(),
            usuario_id=usuario_id,
            agente_id=agente_id,
            conteudo=texto,
            origem="explicita" if explicita else "sintese",
            travada=explicita,
        )
        return await self.armazem.salvar(registro, await self._vetor(texto))

    async def buscar(
        self,
        usuario_id: UUID,
        agente_id: UUID | None,
        consulta: str,
        limite: int = MAX_MEMORIAS_RECUPERADAS,
    ) -> list[RegistroMemoria]:
        limite = max(1, min(limite, MAX_MEMORIAS_RECUPERADAS))
        return await self.armazem.buscar(
            usuario_id, agente_id, consulta, limite, await self._vetor(consulta)
        )

    async def esquecer(self, usuario_id: UUID, memoria_id: UUID) -> bool:
        return await self.armazem.apagar(usuario_id, memoria_id)

    @staticmethod
    def contexto(registros: Sequence[RegistroMemoria]) -> str:
        """Bloco cercado com até 5 memórias para o prompt do agente."""
        return formatar_memorias([(r.conteudo, str(r.id)) for r in registros])

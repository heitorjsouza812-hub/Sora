"""Biblioteca de arquivos (Onda 2, 2026-11-20): tudo o que você enviou ou que os bots criaram,
num lugar só, com pastas, favoritos, "Recentes" (7 dias) e busca por nome.

Os arquivos continuam sendo os anexos (``/v1/anexos/{id}`` baixa). Aqui só se organiza: mover
para uma pasta e marcar favorito. Apagar uma pasta não apaga os arquivos dela; eles voltam para
"Sem pasta".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.tabelas import Anexo, PastaBiblioteca

roteador = APIRouter(
    prefix="/biblioteca", tags=["biblioteca"], dependencies=[Depends(usuario_atual)]
)

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]

MAX_PASTAS = 100
DIAS_RECENTES = 7
Vista = Literal["todos", "recentes", "favoritos", "sem_pasta"]
TipoArquivo = Literal["imagem", "documento", "outro"]

_DOCUMENTOS = (
    "application/pdf",
    "text/",
    "application/msword",
    "application/vnd.openxmlformats",
    "application/vnd.ms-",
    "application/json",
)


class ArquivoSaida(BaseModel):
    id: UUID
    nome: str
    tipo: str
    tamanho: int
    origem: str
    pasta_id: UUID | None
    favorito: bool
    criado_em: datetime


class PaginaArquivos(BaseModel):
    itens: list[ArquivoSaida]
    proximo: datetime | None
    """Passe em ``antes`` para a próxima página (``None`` = acabou)."""


class PastaSaida(BaseModel):
    id: UUID
    nome: str
    total: int
    criada_em: datetime


class PastaEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=60)


class ArquivoAtualizacao(BaseModel):
    pasta_id: UUID | None = None
    favorito: bool | None = None


def _filtro_tipo(tipo: TipoArquivo):
    if tipo == "imagem":
        return Anexo.tipo.like("image/%")
    documento = or_(*(Anexo.tipo.like(f"{prefixo}%") for prefixo in _DOCUMENTOS))
    return documento if tipo == "documento" else ~or_(Anexo.tipo.like("image/%"), documento)


async def _pasta(sessao: AsyncSession, usuario_id: UUID, pasta_id: UUID) -> PastaBiblioteca:
    pasta = await sessao.scalar(
        select(PastaBiblioteca).where(
            PastaBiblioteca.id == pasta_id, PastaBiblioteca.usuario_id == usuario_id
        )
    )
    if pasta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada.")
    return pasta


@roteador.get("/arquivos")
async def listar_arquivos(
    usuario_id: UsuarioId,
    sessao: Sessao,
    vista: Vista = "todos",
    pasta_id: UUID | None = None,
    tipo: TipoArquivo | None = None,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    antes: datetime | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 60,
) -> PaginaArquivos:
    """Do mais novo para o mais antigo, em páginas (``antes`` = ``proximo`` da página anterior)."""
    consulta = select(Anexo).where(Anexo.usuario_id == usuario_id)
    if pasta_id is not None:
        await _pasta(sessao, usuario_id, pasta_id)
        consulta = consulta.where(Anexo.pasta_id == pasta_id)
    elif vista == "sem_pasta":
        consulta = consulta.where(Anexo.pasta_id.is_(None))
    elif vista == "favoritos":
        consulta = consulta.where(Anexo.favorito.is_(True))
    elif vista == "recentes":
        consulta = consulta.where(
            Anexo.criado_em >= datetime.now(UTC) - timedelta(days=DIAS_RECENTES)
        )
    if tipo is not None:
        consulta = consulta.where(_filtro_tipo(tipo))
    if busca and busca.strip():
        termo = busca.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.where(Anexo.nome.ilike(f"%{termo}%", escape="\\"))
    if antes is not None:
        consulta = consulta.where(Anexo.criado_em < antes)
    linhas = list(
        (
            await sessao.scalars(
                consulta.order_by(Anexo.criado_em.desc(), Anexo.id.desc()).limit(limite + 1)
            )
        ).all()
    )
    pagina = linhas[:limite]
    return PaginaArquivos(
        itens=[ArquivoSaida.model_validate(a, from_attributes=True) for a in pagina],
        proximo=pagina[-1].criado_em if len(linhas) > limite else None,
    )


@roteador.patch("/arquivos/{anexo_id}")
async def atualizar_arquivo(
    anexo_id: UUID, dados: ArquivoAtualizacao, usuario_id: UsuarioId, sessao: Sessao
) -> ArquivoSaida:
    """Move para uma pasta (``pasta_id: null`` = Sem pasta) e/ou marca favorito."""
    anexo = await sessao.scalar(
        select(Anexo).where(Anexo.id == anexo_id, Anexo.usuario_id == usuario_id)
    )
    if anexo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")
    if "pasta_id" in dados.model_fields_set:
        if dados.pasta_id is not None:
            await _pasta(sessao, usuario_id, dados.pasta_id)
        anexo.pasta_id = dados.pasta_id
    if dados.favorito is not None:
        anexo.favorito = dados.favorito
    await sessao.flush()
    return ArquivoSaida.model_validate(anexo, from_attributes=True)


@roteador.get("/pastas")
async def listar_pastas(usuario_id: UsuarioId, sessao: Sessao) -> list[PastaSaida]:
    total = (
        select(func.count(Anexo.id))
        .where(Anexo.pasta_id == PastaBiblioteca.id)
        .correlate(PastaBiblioteca)
        .scalar_subquery()
    )
    linhas = (
        await sessao.execute(
            select(PastaBiblioteca, total)
            .where(PastaBiblioteca.usuario_id == usuario_id)
            .order_by(func.lower(PastaBiblioteca.nome))
        )
    ).all()
    return [
        PastaSaida(id=p.id, nome=p.nome, total=int(n or 0), criada_em=p.criada_em)
        for p, n in linhas
    ]


async def _salvar_nome(sessao: AsyncSession, pasta: PastaBiblioteca, nome: str) -> None:
    pasta.nome = " ".join(nome.split())
    try:
        async with sessao.begin_nested():
            await sessao.flush()
    except IntegrityError as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe uma pasta com esse nome."
        ) from erro


@roteador.post("/pastas", status_code=status.HTTP_201_CREATED)
async def criar_pasta(dados: PastaEntrada, usuario_id: UsuarioId, sessao: Sessao) -> PastaSaida:
    total = await sessao.scalar(
        select(func.count(PastaBiblioteca.id)).where(PastaBiblioteca.usuario_id == usuario_id)
    )
    if (total or 0) >= MAX_PASTAS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Use no máximo {MAX_PASTAS} pastas."
        )
    pasta = PastaBiblioteca(usuario_id=usuario_id, nome="")
    sessao.add(pasta)
    await _salvar_nome(sessao, pasta, dados.nome)
    await sessao.refresh(pasta)
    return PastaSaida(id=pasta.id, nome=pasta.nome, total=0, criada_em=pasta.criada_em)


@roteador.patch("/pastas/{pasta_id}")
async def renomear_pasta(
    pasta_id: UUID, dados: PastaEntrada, usuario_id: UsuarioId, sessao: Sessao
) -> PastaSaida:
    pasta = await _pasta(sessao, usuario_id, pasta_id)
    await _salvar_nome(sessao, pasta, dados.nome)
    total = await sessao.scalar(select(func.count(Anexo.id)).where(Anexo.pasta_id == pasta.id))
    return PastaSaida(
        id=pasta.id, nome=pasta.nome, total=int(total or 0), criada_em=pasta.criada_em
    )


@roteador.delete("/pastas/{pasta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_pasta(pasta_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    """Apaga só a pasta; os arquivos dela voltam para "Sem pasta"."""
    pasta = await _pasta(sessao, usuario_id, pasta_id)
    await sessao.execute(update(Anexo).where(Anexo.pasta_id == pasta.id).values(pasta_id=None))
    await sessao.delete(pasta)

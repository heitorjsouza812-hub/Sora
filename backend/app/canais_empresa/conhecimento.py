"""Base de conhecimento da empresa: fusão de itens repetidos, contradição, aprovação e busca.

Quem fala decide o que vale (achado M1 da Cerca-2, 2026-11-15):

- **Conhecimento da empresa** (política, preço/produto, processo, tom de voz) só nasce de fala de
  **funcionário** (origem com ``papel = "funcionario"``). A fala do **cliente** só pode gerar
  ``faq`` (a pergunta) e ``objecao``, e o conteúdo desses itens fica vazio até um funcionário
  responder: texto de cliente nunca vira resposta, política, preço nem instrução. Origem que
  não se sabe qual é conta como cliente.
- **Contradição não troca nada sozinha.** O conteúdo vigente fica; a versão nova vai para
  ``em_disputa`` e o item vira ``contraditorio`` (fora do prompt) até o usuário escolher.
- **Nada entra no prompt sem aprovação.** Item novo nasce ``pendente``; só ``aprovado`` (o
  usuário aprovou ou editou), sem contradição e com conteúdo, é lido pelos bots
  (``condicoes_do_prompt``). A aprovação é item a item (ou em lote por ids); por tipo não há.
- Itens parecidos (mesma categoria e título com palavras em comum) se fundem; a contagem de
  ocorrências conta contatos distintos, não mensagens.
- Item editado pelo usuário (``travado``) nunca é sobrescrito: só conta. Item apagado não volta.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.extracao import MAX_CONTEUDO, MAX_TITULO, ConhecimentoExtraido
from app.canais_empresa.tabelas import ConhecimentoEmpresa

LIMITE_SEMELHANCA_TITULO = 0.7
LIMITE_SEMELHANCA_CONTEUDO = 0.4
MAX_ORIGENS = 20
MAX_ANTERIORES = 10
MAX_EM_DISPUTA = 10

PAPEL_CLIENTE = "cliente"
PAPEL_FUNCIONARIO = "funcionario"
CATEGORIAS_DE_CLIENTE = frozenset({"faq", "objecao"})
"""O que a fala de cliente pode gerar: a pergunta e a objeção, nunca política, preço ou processo."""
ESTADO_PENDENTE = "pendente"
ESTADO_APROVADO = "aprovado"

_PALAVRAS_VAZIAS = frozenset(
    "a o as os um uma uns umas de da do das dos em na no nas nos para por com sem que e ou se "
    "ao aos qual quais como quando onde isso essa esse esta este tem ter foi ser sao era mais "
    "muito voces voce meu minha seu sua nosso nossa vai vou pode podem posso favor".split()
)


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _radical(palavra: str) -> str:
    """ "trocar"/"troca"/"trocas" → "troca": junta as flexões mais comuns."""
    return palavra[:5] if len(palavra) >= 6 else palavra


def palavras(texto: str) -> set[str]:
    return {
        _radical(p)
        for p in re.findall(r"[a-z0-9]+", normalizar(texto))
        if len(p) >= 3 and p not in _PALAVRAS_VAZIAS
    }


def numeros(texto: str) -> set[str]:
    """Prazos, preços e quantidades citados: "7 dias", "R$ 29,90". É o que mais separa duas
    respostas que parecem iguais."""
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", texto)}


def mesmo_conteudo(a: str, b: str) -> bool:
    """Dois conteúdos dizem a mesma coisa? Números diferentes = contradição, mesmo com
    palavras parecidas; sem números vale a semelhança das palavras."""
    if numeros(a) != numeros(b):
        return False
    return semelhanca(palavras(a), palavras(b)) >= LIMITE_SEMELHANCA_CONTEUDO


def semelhanca(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def chave_de(categoria: str, titulo: str) -> str:
    return f"{categoria}:{' '.join(sorted(palavras(titulo))) or normalizar(titulo)}"[:300]


def _agora_iso(instante: datetime) -> str:
    return instante.astimezone(UTC).isoformat()


class ErroConhecimento(Exception):
    """Regra de negócio que impede a ação (a API devolve 409 com a mensagem)."""


@dataclass(slots=True)
class ResultadoDaFusao:
    novos: int = 0
    atualizados: int = 0
    descartados: int = 0  # fala de cliente tentando virar política, preço ou processo
    em_disputa: int = 0  # versões novas que contradizem o item vigente


def papel_da_origem(origem: dict[str, Any]) -> str:
    """``funcionario`` só quando a origem diz; origem sem papel (dado antigo) conta como cliente."""
    return PAPEL_FUNCIONARIO if origem.get("papel") == PAPEL_FUNCIONARIO else PAPEL_CLIENTE


def tem_fala_de_funcionario(item: ConhecimentoEmpresa) -> bool:
    return any(papel_da_origem(o) == PAPEL_FUNCIONARIO for o in item.origens)


def condicoes_do_prompt() -> list[Any]:
    """Filtro SQL do que os bots podem ler (prompt e ``consultar_conhecimento``): aprovado pelo
    usuário, sem contradição aberta, não apagado e com conteúdo."""
    return [
        ConhecimentoEmpresa.estado == ESTADO_APROVADO,
        ConhecimentoEmpresa.contraditorio.is_(False),
        ConhecimentoEmpresa.apagado_em.is_(None),
        func.length(func.btrim(ConhecimentoEmpresa.conteudo)) > 0,
    ]


def entra_no_prompt(item: ConhecimentoEmpresa) -> bool:
    return (
        item.estado == ESTADO_APROVADO
        and not item.contraditorio
        and item.apagado_em is None
        and bool(item.conteudo.strip())
    )


def _contato_ja_contado(item: ConhecimentoEmpresa, origem: dict[str, Any]) -> bool:
    chave = (origem.get("contato_id"), papel_da_origem(origem))
    return any((o.get("contato_id"), papel_da_origem(o)) == chave for o in item.origens)


async def fundir(
    sessao: AsyncSession,
    usuario_id: UUID,
    itens: list[tuple[ConhecimentoExtraido, dict[str, Any], datetime]],
) -> ResultadoDaFusao:
    """Funde os itens extraídos na base. Cada item vem com a origem
    (``{canal, mensagem_id, externo_id, link, em, contato_id, papel}``) e a data da mensagem.

    O ``papel`` da origem (quem escreveu a mensagem de onde o item veio) é decidido pelo
    chamador a partir do canal, nunca pelo modelo."""
    resultado = ResultadoDaFusao()
    cache: dict[str, list[ConhecimentoEmpresa]] = {}
    for item, origem, quando in itens:
        papel = papel_da_origem(origem)
        conteudo = item.conteudo
        if papel == PAPEL_CLIENTE:
            if item.categoria not in CATEGORIAS_DE_CLIENTE:
                resultado.descartados += 1
                continue
            conteudo = ""  # a pergunta fica; a "resposta" de um cliente nunca é conteúdo
        existentes = cache.get(item.categoria)
        if existentes is None:
            existentes = list(
                (
                    await sessao.scalars(
                        select(ConhecimentoEmpresa).where(
                            ConhecimentoEmpresa.usuario_id == usuario_id,
                            ConhecimentoEmpresa.categoria == item.categoria,
                        )
                    )
                ).all()
            )
            cache[item.categoria] = existentes
        chave = chave_de(item.categoria, item.titulo)
        alvo = next((e for e in existentes if e.chave == chave), None)
        if alvo is None:
            pal = palavras(item.titulo)
            melhor = max(
                existentes, key=lambda e: semelhanca(pal, palavras(e.titulo)), default=None
            )
            if (
                melhor is not None
                and semelhanca(pal, palavras(melhor.titulo)) >= LIMITE_SEMELHANCA_TITULO
            ):
                alvo = melhor
        if alvo is None:
            novo = ConhecimentoEmpresa(
                usuario_id=usuario_id,
                categoria=item.categoria,
                chave=chave,
                titulo=item.titulo[:MAX_TITULO],
                conteudo=conteudo[:MAX_CONTEUDO],
                ocorrencias=1,
                origens=[origem],
                primeira_em=quando,
                ultima_em=quando,
                anteriores=[],
                em_disputa=[],
                estado=ESTADO_PENDENTE,
            )
            sessao.add(novo)
            await sessao.flush()
            existentes.append(novo)
            resultado.novos += 1
            continue
        if alvo.apagado_em is not None:
            continue
        if not _contato_ja_contado(alvo, origem):
            alvo.ocorrencias += 1
            alvo.origens = [*alvo.origens, origem][-MAX_ORIGENS:]
        if papel == PAPEL_FUNCIONARIO:
            if not alvo.conteudo.strip():
                # a pergunta de um cliente ganhou a resposta de um funcionário: precisa de revisão
                alvo.conteudo = conteudo[:MAX_CONTEUDO]
                alvo.estado = ESTADO_PENDENTE
                alvo.aprovado_em = None
            elif not mesmo_conteudo(alvo.conteudo, conteudo) and not alvo.travado:
                ja_na_disputa = any(
                    mesmo_conteudo(d.get("conteudo", ""), conteudo) for d in alvo.em_disputa
                )
                if not ja_na_disputa:
                    versao = {
                        "conteudo": conteudo[:MAX_CONTEUDO],
                        "em": _agora_iso(quando),
                        "papel": papel,
                    }
                    alvo.em_disputa = [*alvo.em_disputa, versao][-MAX_EM_DISPUTA:]
                    resultado.em_disputa += 1
                alvo.contraditorio = True
        if quando > alvo.ultima_em:
            alvo.ultima_em = quando
        alvo.atualizado_em = datetime.now(UTC)
        resultado.atualizados += 1
    await sessao.flush()
    return resultado


def aprovar(item: ConhecimentoEmpresa) -> None:
    """O usuário aprova: o item passa a valer para os bots."""
    if item.contraditorio:
        raise ErroConhecimento("Há versões contraditórias: escolha qual vale antes de aprovar.")
    if not item.conteudo.strip():
        raise ErroConhecimento(
            "Esse item é só uma pergunta de cliente, sem resposta de funcionário. "
            "Edite e escreva a resposta para aprovar."
        )
    item.estado = ESTADO_APROVADO
    item.aprovado_em = datetime.now(UTC)
    item.atualizado_em = item.aprovado_em


def resolver_contradicao(item: ConhecimentoEmpresa, versao: int | None) -> None:
    """O usuário decide: ``None`` mantém o conteúdo vigente; ``n`` adota ``em_disputa[n]``
    (o vigente vai para ``anteriores``). Em qualquer caso o item fica aprovado."""
    if not item.contraditorio:
        raise ErroConhecimento("Esse item não tem versões contraditórias.")
    if versao is not None:
        if not 0 <= versao < len(item.em_disputa):
            raise ErroConhecimento("Versão inexistente.")
        escolhida = item.em_disputa[versao]
        item.anteriores = [
            *item.anteriores,
            {"conteudo": item.conteudo, "em": _agora_iso(item.ultima_em)},
        ][-MAX_ANTERIORES:]
        item.conteudo = str(escolhida.get("conteudo", ""))[:MAX_CONTEUDO]
    item.em_disputa = []
    item.contraditorio = False
    aprovar(item)


async def buscar(
    sessao: AsyncSession,
    usuario_id: UUID,
    consulta: str,
    *,
    categoria: str | None = None,
    limite: int = 5,
    so_do_prompt: bool = False,
) -> list[ConhecimentoEmpresa]:
    """Busca por palavras (sem acento). Só itens do usuário e não apagados; empate: o mais
    repetido e depois o mais recente. ``so_do_prompt``: só o que os bots podem ler
    (aprovado, sem contradição, com conteúdo)."""
    termos = palavras(consulta)
    if not termos:
        return []
    consulta_sql = select(ConhecimentoEmpresa).where(
        ConhecimentoEmpresa.usuario_id == usuario_id, ConhecimentoEmpresa.apagado_em.is_(None)
    )
    if categoria:
        consulta_sql = consulta_sql.where(ConhecimentoEmpresa.categoria == categoria)
    if so_do_prompt:
        consulta_sql = consulta_sql.where(*condicoes_do_prompt())
    pontuados: list[tuple[float, ConhecimentoEmpresa]] = []
    for item in (await sessao.scalars(consulta_sql.limit(5_000))).all():
        no_titulo = termos & palavras(item.titulo)
        no_conteudo = termos & palavras(item.conteudo)
        ponto = 2 * len(no_titulo) + len(no_conteudo - no_titulo)
        if ponto:
            pontuados.append((ponto + math.log1p(item.ocorrencias) / 10, item))
    pontuados.sort(key=lambda par: (par[0], par[1].ultima_em), reverse=True)
    return [item for _, item in pontuados[:limite]]


def texto_do_item(item: ConhecimentoEmpresa) -> str:
    return f"[{item.categoria}] {item.titulo}: {item.conteudo} (visto {item.ocorrencias}x)"

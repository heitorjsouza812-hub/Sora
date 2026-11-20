"""Exportar meus dados (LGPD, art. 18: acesso e portabilidade).

Um ``.zip`` com tudo o que é do usuário, em JSON legível, e os arquivos enviados ou criados:

- ``LEIA-ME.txt``: o que tem dentro, o que ficou de fora e por quê;
- ``conta.json``: nome, e-mail e preferências;
- ``dados/<tabela>.json``: as linhas de cada tabela que pertencem ao usuário;
- ``arquivos/<id>-<nome>``: os anexos.

As tabelas e as linhas vêm de ``contas.condicoes_do_usuario`` (derivadas das chaves estrangeiras),
a mesma regra do "apagar conta": tabela nova entra na exportação sozinha. Ficam de fora só os
segredos e o que não serve para a pessoa: colunas cifradas (chaves de API, logins do navegador,
segredos dos canais), hashes de senha e de token, e vetores de busca.
"""

from __future__ import annotations

import asyncio
import base64
import enum
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Column, LargeBinary, Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas.arquivos import CaminhoInseguro, caminho_do_anexo
from app.modelos.tabelas import Anexo, Usuario

TABELAS_FORA = frozenset({"tokens_email"})
"""Só guardam hashes de links de e-mail: nada que sirva para a pessoa."""

_COLUNA_SECRETA = re.compile(r"(^|_)(hash|hashes|cifrad[oa]s?|segredos?|senha)(_|$)")

LIMITE_POR_HORA = (3, 60 * 60)
"""Exportações por usuário por hora: o arquivo pode ser grande."""

_NOME_SEGURO = re.compile(r"[^\w.\- ]+", re.UNICODE)


def coluna_exportavel(coluna: Column[Any]) -> bool:
    """Fica de fora: binário (sempre cifrado na Sora), vetor de busca e segredo pelo nome."""
    if isinstance(coluna.type, LargeBinary):
        return False
    if type(coluna.type).__name__ == "Vetor":
        return False
    return not _COLUNA_SECRETA.search(coluna.name)


def valor_json(valor: Any) -> Any:
    """Converte o valor do banco para JSON legível."""
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, (UUID, Decimal)):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, enum.Enum):
        return valor.value
    if isinstance(valor, (IPv4Address, IPv6Address, IPv4Network, IPv6Network)):
        return str(valor)
    if isinstance(valor, dict):
        return {str(k): valor_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [valor_json(v) for v in valor]
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(valor)).decode()
    return str(valor)


def nome_de_arquivo(anexo_id: UUID, nome: str) -> str:
    """``arquivos/<id>-<nome>``: o id evita colisão; o nome perde barras e caracteres estranhos."""
    limpo = _NOME_SEGURO.sub("_", nome).strip(" .") or "arquivo"
    return f"arquivos/{anexo_id}-{limpo[:120]}"


@dataclass
class ResumoExportacao:
    linhas_por_tabela: dict[str, int] = field(default_factory=dict)
    arquivos: int = 0
    arquivos_faltando: int = 0


def _leia_me(resumo: ResumoExportacao, agora: datetime) -> str:
    tabelas = "\n".join(
        f"  - dados/{nome}.json: {total} registro(s)"
        for nome, total in sorted(resumo.linhas_por_tabela.items())
        if total
    )
    faltando = (
        f"\n{resumo.arquivos_faltando} arquivo(s) não estavam mais no servidor e ficaram de fora.\n"
        if resumo.arquivos_faltando
        else ""
    )
    return (
        "Seus dados na Sora\n"
        "==================\n\n"
        f"Exportado em {agora.strftime('%d/%m/%Y às %H:%M')} (UTC).\n\n"
        "O que tem aqui\n"
        "- conta.json: seu nome, e-mail e preferências.\n"
        "- dados/: tudo o que a Sora guarda da sua conta (conversas, mensagens, bots, grupos,\n"
        "  rotinas, memórias, habilidades, uso dos modelos e o resto), um arquivo JSON por tipo.\n"
        f"{tabelas}\n"
        f"- arquivos/: {resumo.arquivos} arquivo(s) que você enviou ou que os bots criaram.\n"
        f"{faltando}\n"
        "O que ficou de fora, e por quê\n"
        "- Sua senha e os códigos de login: só existem como hash, que não serve para nada fora\n"
        "  da Sora.\n"
        "- Chaves de API, logins salvos no navegador dos bots e segredos dos canais: ficam\n"
        "  cifrados e não saem do servidor. Você continua vendo o final de cada chave.\n"
        "- Vetores de busca da memória: são números calculados a partir do texto, que já está\n"
        "  aqui.\n"
        "- O rascunho interno dos modelos durante cada resposta: as mensagens e os resultados\n"
        "  estão aqui; o passo a passo interno do modelo não é guardado para você.\n\n"
        "Para apagar tudo, use Configurações → Conta → Apagar conta.\n"
    )


async def _linhas(sessao: AsyncSession, tabela: Table, condicao: Any) -> list[dict[str, Any]]:
    colunas = [c for c in tabela.columns if coluna_exportavel(c)]
    if not colunas:
        return []
    ordem = list(tabela.primary_key.columns) or colunas[:1]
    resultado = await sessao.execute(select(*colunas).where(condicao).order_by(*ordem))
    return [{c: valor_json(v) for c, v in linha.items()} for linha in resultado.mappings()]


def _escrever(zip_: zipfile.ZipFile, nome: str, conteudo: Any) -> None:
    if not isinstance(conteudo, str):
        conteudo = json.dumps(conteudo, ensure_ascii=False, indent=2)
    zip_.writestr(nome, conteudo.encode("utf-8"))


async def gerar_exportacao(
    sessao: AsyncSession,
    usuario_id: UUID,
    destino: Path,
    raiz_arquivos: Path,
    agora: datetime,
) -> ResumoExportacao:
    """Grava o ``.zip`` em ``destino``. O banco é lido aqui; o disco, em thread."""
    from app.core.contas import condicoes_do_usuario

    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise LookupError("Conta não encontrada.")
    resumo = ResumoExportacao()
    zip_ = await asyncio.to_thread(zipfile.ZipFile, destino, "w", zipfile.ZIP_DEFLATED)
    try:
        conta = {
            "nome": usuario.nome,
            "email": usuario.email,
            "idioma": usuario.idioma,
            "plano": usuario.plano,
            "prioridade": valor_json(usuario.prioridade),
            "email_verificado_em": valor_json(usuario.email_verificado_em),
            "criado_em": valor_json(usuario.criado_em),
            "exportado_em": agora.isoformat(),
        }
        await asyncio.to_thread(_escrever, zip_, "conta.json", conta)

        for tabela, condicao in condicoes_do_usuario(usuario_id).items():
            if tabela.name in TABELAS_FORA:
                continue
            linhas = await _linhas(sessao, tabela, condicao)
            resumo.linhas_por_tabela[tabela.name] = len(linhas)
            if linhas:
                await asyncio.to_thread(_escrever, zip_, f"dados/{tabela.name}.json", linhas)

        anexos = (
            await sessao.execute(
                select(Anexo.id, Anexo.nome, Anexo.caminho)
                .where(Anexo.usuario_id == usuario_id)
                .order_by(Anexo.criado_em)
            )
        ).all()
        for anexo_id, nome, caminho in anexos:
            try:
                origem = caminho_do_anexo(raiz_arquivos, caminho)
            except CaminhoInseguro:
                resumo.arquivos_faltando += 1
                continue
            if not await asyncio.to_thread(origem.is_file):
                resumo.arquivos_faltando += 1
                continue
            await asyncio.to_thread(zip_.write, origem, nome_de_arquivo(anexo_id, nome))
            resumo.arquivos += 1

        await asyncio.to_thread(_escrever, zip_, "LEIA-ME.txt", _leia_me(resumo, agora))
    finally:
        await asyncio.to_thread(zip_.close)
    return resumo

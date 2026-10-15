"""Ferramenta ``ler_anexo`` (especificação §4; tabela ``anexos`` em §1). Só lê
anexos do próprio usuário; o conteúdo entra na cerca ``<dado_externo>``.

O modelo não passa caminho nenhum, só o ``anexo_id`` (UUID validado). As travas:
a consulta filtra por ``anexos.usuario_id = contexto.usuario_id`` (anexo de
outro usuário = "não encontrado") e o ``anexos.caminho`` salvo passa por
``app.ferramentas.arquivos.caminho_do_anexo``, que confere o caminho resolvido
dentro do volume de arquivos.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta


class LerAnexo(BaseModel):
    """Lê um arquivo enviado pelo usuário ou gerado por um especialista."""

    anexo_id: UUID


async def ler_anexo(args: LerAnexo, contexto: ContextoFerramenta) -> str:
    """Lê o anexo (texto, PDF, planilha, documento) e devolve o conteúdo cercado."""
    raise NotImplementedError

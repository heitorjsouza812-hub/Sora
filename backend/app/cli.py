"""Ferramentas administrativas locais do backend da Sora."""

import argparse
import asyncio
import secrets
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.core.banco import fabrica_sessoes
from app.modelos.tabelas import Convite


class ErroCli(Exception):
    """Erro esperado, exibido sem traceback para quem opera o ambiente local."""


def _usos_positivos(valor: str) -> int:
    try:
        usos = int(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("--usos precisa ser um número inteiro.") from erro
    if usos < 1:
        raise argparse.ArgumentTypeError("--usos precisa ser maior que zero.")
    return usos


def _novo_codigo() -> str:
    return f"SORA-{secrets.token_urlsafe(12).upper()}"


def _codigo_valido(codigo: str | None) -> str:
    codigo = codigo.strip() if codigo is not None else _novo_codigo()
    if not codigo:
        raise ErroCli("O código do convite não pode ser vazio.")
    if len(codigo) > 256:
        raise ErroCli("O código do convite pode ter no máximo 256 caracteres.")
    return codigo


async def criar_convite(codigo: str | None, usos: int) -> str:
    """Cria um convite no banco configurado e devolve o código persistido."""
    codigo_final = _codigo_valido(codigo)
    fabrica = fabrica_sessoes()
    async with fabrica() as sessao:
        sessao.add(Convite(codigo=codigo_final, usos_restantes=usos))
        try:
            await sessao.commit()
        except IntegrityError as erro:
            await sessao.rollback()
            raise ErroCli(f'O convite "{codigo_final}" já existe.') from erro
    return codigo_final


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    recursos = parser.add_subparsers(dest="recurso", required=True)
    convite = recursos.add_parser("convite", help="Gerencia convites de cadastro.")
    acoes = convite.add_subparsers(dest="acao", required=True)
    criar = acoes.add_parser("criar", help="Cria um convite no banco configurado.")
    criar.add_argument("--codigo", help="Código desejado; se omitido, gera um código seguro.")
    criar.add_argument(
        "--usos", type=_usos_positivos, default=1, help="Número de usos (padrão: 1)."
    )
    return parser


def executar(argv: Sequence[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    try:
        codigo = asyncio.run(criar_convite(argumentos.codigo, argumentos.usos))
    except ErroCli as erro:
        construir_parser().error(str(erro))
    print(f"Convite criado: {codigo} ({argumentos.usos} uso(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())

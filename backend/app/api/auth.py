"""Rotas de cadastro, login, renovação e saída; especificação §8.2."""

from fastapi import APIRouter, Response, status

from app.modelos.esquemas import CadastroEntrada, LoginEntrada, RenovacaoEntrada, TokensSaida

roteador = APIRouter(prefix="/auth", tags=["auth"])


@roteador.post("/cadastrar", status_code=status.HTTP_201_CREATED)
async def cadastrar(dados: CadastroEntrada) -> None:
    """Cadastra uma conta mediante convite."""
    raise NotImplementedError


@roteador.post("/entrar")
async def entrar(dados: LoginEntrada, resposta: Response) -> TokensSaida:
    """Autentica e devolve os tokens adequados ao cliente."""
    raise NotImplementedError


@roteador.post("/renovar")
async def renovar(dados: RenovacaoEntrada, resposta: Response) -> TokensSaida:
    """Rotaciona o token de renovação e emite novo acesso."""
    raise NotImplementedError


@roteador.post("/sair", status_code=status.HTTP_204_NO_CONTENT)
async def sair(dados: RenovacaoEntrada, resposta: Response) -> None:
    """Encerra a sessão atual e remove o cookie quando aplicável."""
    raise NotImplementedError

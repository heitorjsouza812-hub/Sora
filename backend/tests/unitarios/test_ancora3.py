"""Normalização e limites das fontes e captura de texto parcial."""

from app.agentes.middleware.conversa import TextoParcial, coletar_fontes


def test_fontes_deduplicadas_preservam_titulo_e_ordem():
    fontes = []
    coletar_fontes(
        "1. Documento oficial\n https://EXAMPLE.com/artigo#secao\n"
        "2. Repetido\n https://example.com/artigo\n"
        "Título: Outra página\nEndereço: http://example.org/pagina",
        fontes,
    )
    assert fontes == [
        dict(
            n=1, titulo="Documento oficial", url="https://example.com/artigo", dominio="example.com"
        ),
        dict(n=2, titulo="Outra página", url="http://example.org/pagina", dominio="example.org"),
    ]


def test_fontes_aceitam_apenas_http_https_e_limitam_dez():
    fontes = []
    coletar_fontes(
        "javascript:alert(1) file:///etc/passwd ftp://example.com\n"
        "https://user:senha@example.com/ https://[invalido\n"
        + "\n".join(f"https://example.com/{i}" for i in range(15)),
        fontes,
    )
    assert len(fontes) == 10
    assert [f["n"] for f in fontes] == list(range(1, 11))
    assert fontes[-1]["url"] == "https://example.com/9"


async def test_texto_parcial_recupera_argumento_incompleto():
    parcial = TextoParcial()
    parcial.argumentos = '{"texto": "Resposta ainda parcial'
    assert parcial.parcial() == "Resposta ainda parcial"
    parcial.argumentos = ""
    await parcial.on_llm_new_token("Olá")
    assert parcial.parcial() == "Olá"

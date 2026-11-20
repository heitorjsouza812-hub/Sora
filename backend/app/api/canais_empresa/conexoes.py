"""Conexões com Slack e WhatsApp Business: salvar, testar, escolher canais."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from pydantic import BaseModel

from app.api.canais_empresa.comum import (
    Sessao,
    Usuario,
    roteador,
)
from app.api.canais_empresa.esquemas import (
    CanaisEscolhidosEntrada,
    ConexaoEntrada,
    ConexaoSaida,
    TesteSaida,
    _erro,
)
from app.canais_empresa import clientes, conexoes
from app.canais_empresa.tabelas import (
    ConexaoCanalEmpresa,
)


def _saida_conexao(canal: str, c: ConexaoCanalEmpresa | None) -> ConexaoSaida:
    escopos = list(clientes.ESCOPOS_DE_LEITURA) if canal == "slack" else []
    if c is None:
        return ConexaoSaida(canal=canal, configurada=False, escopos_slack=escopos)
    try:
        definidos = set(conexoes.decifrar_segredos(c))
    except Exception:
        definidos = set()
    return ConexaoSaida(
        canal=canal,
        configurada=True,
        id=c.id,
        rotulo=c.rotulo,
        ativa=c.ativa,
        config=c.config,
        segredos_definidos={k: k in definidos for k in conexoes.SEGREDOS_DO_CANAL[canal]},
        canais_escolhidos=c.canais_escolhidos,
        webhook_caminho=conexoes.caminho_do_webhook(c),
        ultimo_teste_em=c.ultimo_teste_em,
        ultimo_teste_ok=c.ultimo_teste_ok,
        ultimo_teste_detalhe=c.ultimo_teste_detalhe,
        escopos_slack=escopos,
    )


@roteador.get("/conexoes")
async def listar_conexoes(usuario_id: Usuario, sessao: Sessao) -> list[ConexaoSaida]:
    return [
        _saida_conexao(canal, await conexoes.obter(sessao, usuario_id, canal))
        for canal in conexoes.CANAIS
    ]


@roteador.put("/conexoes/{canal}")
async def salvar_conexao(
    canal: str, dados: ConexaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> ConexaoSaida:
    """Cria ou atualiza a conexão. Na atualização, segredo omitido é mantido."""
    try:
        conexoes.validar_canal(canal)
        existente = await conexoes.obter(sessao, usuario_id, canal)
        novos = conexoes.limpar_segredos(canal, dados.segredos, completo=existente is None)
        config = (
            conexoes.limpar_config(canal, dados.config, completo=True)
            if existente is None
            else {**existente.config, **conexoes.limpar_config(canal, dados.config, completo=False)}
        )
    except conexoes.ErroConexao as erro:
        raise _erro(erro) from erro
    if existente is None:
        existente = ConexaoCanalEmpresa(
            usuario_id=usuario_id,
            canal=canal,
            rotulo=(dados.rotulo or "").strip(),
            config=config,
            segredos=conexoes.cifrar_segredos(novos, usuario_id=usuario_id, canal=canal),
            canais_escolhidos=[],
            ativa=True if dados.ativa is None else dados.ativa,
        )
        sessao.add(existente)
    else:
        if novos:
            atuais = conexoes.decifrar_segredos(existente)
            existente.segredos = conexoes.cifrar_segredos(
                {**atuais, **novos}, usuario_id=usuario_id, canal=canal
            )
            existente.ultimo_teste_ok = None
        existente.config = config
        if dados.rotulo is not None:
            existente.rotulo = dados.rotulo.strip()
        if dados.ativa is not None:
            existente.ativa = dados.ativa
        existente.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_conexao(canal, existente)


@roteador.delete("/conexoes/{canal}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conexao(canal: str, usuario_id: Usuario, sessao: Sessao) -> None:
    """Remove a conexão **e tudo que veio dela** (contatos, mensagens e fichas)."""
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    await sessao.delete(c)


@roteador.put("/conexoes/{canal}/canais")
async def escolher_canais(
    canal: str, dados: CanaisEscolhidosEntrada, usuario_id: Usuario, sessao: Sessao
) -> ConexaoSaida:
    """Os canais do Slack (ids) ou o número do WhatsApp (phone_number_id) que a Sora lê.
    Só o que estiver aqui entra; o resto do workspace é ignorado."""
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    try:
        c.canais_escolhidos = conexoes.validar_canais_escolhidos(canal, dados.canais)
    except conexoes.ErroConexao as erro:
        raise _erro(erro) from erro
    c.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return _saida_conexao(canal, c)


@roteador.post("/conexoes/{canal}/testar")
async def testar_conexao(canal: str, usuario_id: Usuario, sessao: Sessao) -> TesteSaida:
    c = await conexoes.obter(sessao, usuario_id, canal) if canal in conexoes.CANAIS else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    segredos = conexoes.decifrar_segredos(c)
    avisos: list[str] = []
    try:
        http = clientes.fabrica_http()
        if canal == "slack":
            info = await clientes.ClienteSlackLeitura(segredos["bot_token"], cliente=http).testar()
            escrita = clientes.escopos_de_escrita(info["escopos"])
            if escrita:
                resultado = TesteSaida(
                    ok=False,
                    detalhe=(
                        "Este token pode enviar mensagens (" + ", ".join(escrita) + "). A Sora só "
                        "lê: reinstale o app do Slack só com "
                        + ", ".join(clientes.ESCOPOS_DE_LEITURA)
                        + "."
                    ),
                )
            else:
                faltam = sorted(set(clientes.ESCOPOS_DE_LEITURA) - set(info["escopos"]))
                if info["escopos"] and faltam:
                    avisos.append("Faltam escopos de leitura: " + ", ".join(faltam) + ".")
                c.config = {
                    **c.config,
                    "team_id": info["team_id"],
                    "bot_user_id": info["user_id"],
                    **({"workspace": info["team"]} if info["team"] else {}),
                }
                resultado = TesteSaida(
                    ok=True, detalhe=f"Conectado ao workspace {info['team'] or info['team_id']}."
                )
        else:
            info = await clientes.ClienteWhatsAppLeitura(
                segredos["access_token"], cliente=http
            ).testar(str(c.config.get("phone_number_id", "")))
            c.config = {
                **c.config,
                "numero_exibicao": info["numero"] or c.config.get("numero_exibicao", ""),
            }
            resultado = TesteSaida(
                ok=True,
                detalhe=(
                    f"Número {info['numero'] or c.config.get('phone_number_id')} ({info['nome']})."
                ),
            )
    except clientes.ErroCanalEmpresa as erro:
        resultado = TesteSaida(ok=False, detalhe=str(erro))
    resultado.avisos = avisos
    c.ultimo_teste_em = datetime.now(UTC)
    c.ultimo_teste_ok = resultado.ok
    c.ultimo_teste_detalhe = resultado.detalhe
    await sessao.flush()
    return resultado


class CanalDoSlack(BaseModel):
    id: str
    nome: str
    privado: bool


@roteador.get("/conexoes/slack/canais-disponiveis")
async def canais_disponiveis(usuario_id: Usuario, sessao: Sessao) -> list[CanalDoSlack]:
    """Canais que o bot do Slack enxerga, para o usuário marcar quais a Sora lê."""
    c = await conexoes.obter(sessao, usuario_id, "slack")
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexão não encontrada.")
    try:
        lista = await clientes.ClienteSlackLeitura(
            conexoes.decifrar_segredos(c)["bot_token"], cliente=clientes.fabrica_http()
        ).listar_canais()
    except clientes.ErroCanalEmpresa as erro:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(erro)) from erro
    return [CanalDoSlack(**item) for item in lista]

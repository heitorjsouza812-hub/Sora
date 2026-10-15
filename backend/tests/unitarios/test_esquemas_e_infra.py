"""Esquemas de saída coerentes com o ORM, worker e arquivos de infra."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.modelos.enumeracoes import TipoEntrega
from app.modelos.esquemas import AnexoSaida, EntregaSaida
from app.modelos.tabelas import Anexo

RAIZ = Path(__file__).resolve().parents[3]


def test_anexo_saida_le_o_id_do_orm_e_serializa_anexo_id() -> None:
    anexo = Anexo(
        id=uuid4(),
        usuario_id=uuid4(),
        nome="a.pdf",
        tipo="application/pdf",
        tamanho=3,
        caminho="/x",
        origem="usuario",
        criado_em=datetime.now(UTC),
    )
    saida = AnexoSaida.model_validate(anexo)
    assert saida.anexo_id == anexo.id
    assert saida.model_dump(mode="json")["anexo_id"] == str(anexo.id)
    assert (
        AnexoSaida.model_validate(
            {"anexo_id": str(anexo.id), "nome": "a", "tipo": "t", "tamanho": 1}
        ).anexo_id
        == anexo.id
    )


def test_entrega_aceita_dict_lista_e_texto() -> None:
    base = {
        "id": uuid4(),
        "agente_id": None,
        "versao": 1,
        "tipo": TipoEntrega.TEXTO,
        "titulo": "t",
        "resumo": "r",
    }
    for conteudo in ({"a": 1}, [{"a": 1}], "texto"):
        assert EntregaSaida(**base, conteudo=conteudo).conteudo == conteudo


def test_worker_usa_a_redis_url_da_configuracao() -> None:
    from workers.configuracao import WorkerSettings

    assert WorkerSettings.redis_settings.host == "localhost"  # REDIS_URL do conftest
    assert WorkerSettings.redis_settings.port == 6379


def test_scripts_de_backup_param_no_erro_e_conferem_o_arquivo() -> None:
    for nome in ("backup-postgres.sh", "backup-anexos.sh", "testar-restauracao.sh"):
        assert "set -euo pipefail" in (RAIZ / "infra/scripts" / nome).read_text(encoding="utf-8")
    texto = (RAIZ / "infra/scripts/backup-postgres.sh").read_text(encoding="utf-8")
    assert texto.index('-s "${arquivo}"') < texto.index("-delete")


def test_compose_e_caddy_atras_do_proxy() -> None:
    compose = (RAIZ / "infra/docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("--no-sync") == 2
    assert "--proxy-headers" in compose and "--forwarded-allow-ips=172.28.0.0/16" in compose
    caddy = (RAIZ / "infra/Caddyfile").read_text(encoding="utf-8")
    assert "text/event-stream" in caddy and "flush_interval -1" in caddy


def _casa_no_caddy(padrao: str, caminho: str) -> bool:
    """Matcher `path` do Caddy: `*` no fim casa tudo; no meio não atravessa `/`."""
    import re

    if padrao.endswith("/*"):
        prefixo = re.escape(padrao[:-1]).replace(r"\*", "[^/]*")
        return re.fullmatch(prefixo + ".*", caminho) is not None
    return re.fullmatch(re.escape(padrao).replace(r"\*", "[^/]*"), caminho) is not None


def test_rotas_sse_da_api_caem_no_handler_sem_compressao_do_caddy() -> None:
    from app.main import app

    caddy = (RAIZ / "infra/Caddyfile").read_text(encoding="utf-8")
    linha = next(x for x in caddy.splitlines() if x.strip().startswith("@eventos path"))
    padroes = linha.split()[2:]
    rotas_sse = [p for p in app.openapi()["paths"] if p.endswith("/eventos")]
    assert len(rotas_sse) >= 2
    for rota in rotas_sse:
        exemplo = rota.replace("{conversa_id}", str(uuid4()))
        assert any(_casa_no_caddy(p, exemplo) for p in padroes), rota

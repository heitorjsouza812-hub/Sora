"""Liga as ferramentas do Relógio no registro (``app/ferramentas/registro.py``)."""

from __future__ import annotations

from pydantic import BaseModel


def registrar(esquemas: dict[str, type[BaseModel]], modulos: dict[str, str]) -> None:
    from app.computador import ExecutarComando
    from app.conectores.servidores import AdicionarServidorMCP
    from app.rotinas.agenda import Agendar, CancelarAgendamento, ListarAgendamentos

    esquemas.update(
        {
            "agendar": Agendar,
            "listar_agendamentos": ListarAgendamentos,
            "cancelar_agendamento": CancelarAgendamento,
            "executar_comando": ExecutarComando,
            "adicionar_servidor_mcp": AdicionarServidorMCP,
        }
    )
    modulos.update(
        {
            "agendar": "app.rotinas.ferramentas",
            "listar_agendamentos": "app.rotinas.ferramentas",
            "cancelar_agendamento": "app.rotinas.ferramentas",
            "executar_comando": "app.computador.ferramenta",
            "adicionar_servidor_mcp": "app.conectores.ferramenta",
        }
    )

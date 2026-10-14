"""Workers ARQ da Sora (especificação §6, "Execução das cadeias na fila").

Os jobs ficam atrás de ``enfileirar()`` (``fila.py``) para dar para trocar o
ARQ por Celery ou Taskiq sem mexer no resto. Para subir:
``uv run arq workers.configuracao.WorkerSettings``.
"""

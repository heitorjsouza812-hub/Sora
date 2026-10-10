import { EditarAgenteModal } from './EditarAgenteModal';
import { fecharEditorAgente, useEditorAberto } from './editorAberto';

/** Monte UMA vez (no AppShell). Mostra o "Editar agente" quando abrirEditorAgente(id) é chamado. */
export function EditorAgenteHost() {
  const id = useEditorAberto();
  return id ? <EditarAgenteModal key={id} agenteId={id} onFechar={fecharEditorAgente} /> : null;
}

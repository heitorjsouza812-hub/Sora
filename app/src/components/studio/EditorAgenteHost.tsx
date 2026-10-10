import { fecharEditorAgente, useEditorAberto } from './abrirEditor';
import { PainelEditarAgente } from './PainelEditarAgente';

/** Monte UMA vez (ex.: no AppShell). Renderiza o painel quando abrirEditorAgente(id) é chamado. */
export function EditorAgenteHost() {
  const id = useEditorAberto();
  return id ? <PainelEditarAgente agenteId={id} onFechar={fecharEditorAgente} /> : null;
}

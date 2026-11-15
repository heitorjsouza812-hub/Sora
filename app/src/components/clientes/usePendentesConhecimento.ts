import { canaisEmpresa } from '../../api/canaisEmpresa';
import { useRevisaoClientes } from '../../state/clientes';
import { useConsulta } from './comum';

/** Itens que esperam o usuário: pendentes de aprovação e contradições abertas. */
export function usePendentesConhecimento() {
  const revisao = useRevisaoClientes();
  const c = useConsulta(`pendentes-conhecimento:${revisao.conhecimento}`, async signal => {
    const [pendentes, disputas] = await Promise.all([canaisEmpresa.conhecimento('', '', 0, signal, 'pendente'), canaisEmpresa.disputas(signal)]);
    const ids = new Set(disputas.map(d => d.id));
    return { disputas, pendentes: pendentes.filter(p => !ids.has(p.id)) };
  });
  return { ...c, total: c.dados ? c.dados.disputas.length + c.dados.pendentes.length : 0 };
}

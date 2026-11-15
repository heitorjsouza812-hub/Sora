import { useBots } from '../../state/bots';
import { useGrupos } from '../../state/grupos';
import { COR_SORA_PEDIDO } from './rotulos';
import type { PedidoAtencao } from './tipos';

/** De quem é o pedido: bot (com a cor dele) e, se vier de um grupo, o nome do grupo. */
export function useOrigemDoPedido(pedido: Pick<PedidoAtencao, 'botId' | 'grupoId'>) {
  const bots = useBots();
  const grupos = useGrupos().lista;
  const bot = pedido.botId ? bots.find(item => item.id === pedido.botId) : undefined;
  const grupo = pedido.grupoId ? grupos.find(item => item.id === pedido.grupoId) : undefined;
  // O agente de um pedido que não é de nenhum bot é a Sora (o chefe de equipe).
  const nome = bot?.nome ?? (pedido.botId || pedido.grupoId ? 'Sora' : null);
  return { nome, cor: bot?.cor ?? COR_SORA_PEDIDO, movimento: bot?.movimento, grupo: grupo?.nome ?? null, grupoId: pedido.grupoId ?? null };
}

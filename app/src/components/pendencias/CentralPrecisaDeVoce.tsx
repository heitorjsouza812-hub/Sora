// Central "Precisa de você": tudo que espera uma decisão do usuário, de qualquer bot, grupo ou da Sora,
// resolvido num lugar só. O contador da barra lateral é o tamanho desta lista, então zera ao resolver.
import { Link } from 'react-router-dom';
import { Modal } from '../overlay';
import { useBots } from '../../state/bots';
import { usePrecisaDeVoce } from '../../state/atencao';
import { CartaoPrecisaDeVoce } from './CartaoPrecisaDeVoce';
import type { PedidoAtencao } from './tipos';
import './pendencias.css';

function Pedido({ pedido, aoNavegar }: { pedido: PedidoAtencao; aoNavegar: () => void }) {
  const bots = useBots();
  const destino = pedido.grupoId ? `/grupos/${pedido.grupoId}` : pedido.botId && bots.some(bot => bot.id === pedido.botId) ? `/bots/${pedido.botId}` : pedido.botId ? '/' : null;
  return <li className="pend-central-item">
    <CartaoPrecisaDeVoce pedido={pedido} />
    {destino && <Link className="pend-central-link" to={destino} onClick={aoNavegar}>{pedido.grupoId ? 'Abrir o grupo' : pedido.botId && destino !== '/' ? 'Abrir a conversa com o bot' : 'Abrir a conversa com a Sora'}</Link>}
  </li>;
}

export function CentralPrecisaDeVoce({ aberta, onFechar }: { aberta: boolean; onFechar: () => void }) {
  const { lista, carregado, erro } = usePrecisaDeVoce();
  return <Modal open={aberta} onClose={onFechar} title="Precisa de você" description={lista.length ? `${lista.length} ${lista.length === 1 ? 'pedido espera' : 'pedidos esperam'} uma decisão sua.` : undefined} size="lg">
    {erro && !lista.length && <p className="pend-erro" role="alert">{erro}</p>}
    {!lista.length && carregado && !erro && <p className="pend-nota" role="status">Nada espera por você agora. Quando um bot, um grupo ou a Sora precisar de uma decisão, o pedido aparece aqui.</p>}
    {!lista.length && !carregado && !erro && <p className="pend-nota" role="status">Carregando pedidos…</p>}
    {!!lista.length && <ul className="pend-central" aria-label="Pedidos que esperam você">{lista.map(pedido => <Pedido key={pedido.id} pedido={pedido} aoNavegar={onFechar} />)}</ul>}
  </Modal>;
}

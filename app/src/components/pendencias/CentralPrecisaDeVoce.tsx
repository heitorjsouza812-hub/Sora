// Central "Precisa de você": tudo que espera uma decisão do usuário, de qualquer bot, grupo ou da Sora,
// resolvido num lugar só. O contador da barra lateral é o tamanho desta lista, então desce junto com a faixa.
import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { Modal } from '../overlay';
import { SoraOrb } from '../mascot';
import { useBots } from '../../state/bots';
import { usePrecisaDeVoce } from '../../state/atencao';
import { CartaoPrecisaDeVoce } from './CartaoPrecisaDeVoce';
import { DURACAO_FAIXA, usePedidosComSaida } from './usePedidosComSaida';
import type { PedidoAtencao } from './tipos';
import './pendencias.css';

function Pedido({ pedido, saindo, aoNavegar }: { pedido: PedidoAtencao; saindo: boolean; aoNavegar: () => void }) {
  const bots = useBots();
  const destino = pedido.grupoId ? `/grupos/${pedido.grupoId}` : pedido.botId && bots.some(bot => bot.id === pedido.botId) ? `/bots/${pedido.botId}` : pedido.botId ? '/' : null;
  const texto = pedido.grupoId ? 'Abrir o grupo' : pedido.botId && destino !== '/' ? 'Abrir a conversa com o bot' : 'Abrir a conversa com a Sora';
  const atalho = destino ? <Link className="pend-central-link" to={destino} onClick={aoNavegar}>{texto}<span aria-hidden="true"> ›</span></Link> : undefined;
  return <li className="pend-central-item" data-saindo={saindo || undefined} style={{ '--saida': `${DURACAO_FAIXA}ms` } as CSSProperties}>
    <div className="pend-central-conteudo"><CartaoPrecisaDeVoce pedido={pedido} faixa atalho={atalho} /></div>
  </li>;
}

export function CentralPrecisaDeVoce({ aberta, onFechar }: { aberta: boolean; onFechar: () => void }) {
  const { lista, carregado, erro } = usePrecisaDeVoce();
  const visiveis = usePedidosComSaida(lista, DURACAO_FAIXA);
  return <Modal open={aberta} onClose={onFechar} title="Precisa de você" className="pend-modal" description={lista.length ? `${lista.length} ${lista.length === 1 ? 'pedido espera' : 'pedidos esperam'} uma decisão sua.` : undefined}>
    {erro && !lista.length && <p className="pend-erro" role="alert">{erro}</p>}
    {!lista.length && !visiveis.length && carregado && !erro && <div className="pend-vazia" role="status">
      <SoraOrb size={56} color="#E2ECFF" state="idle" glow={false} decorative seed={5} />
      <h3>Nada espera por você agora.</h3>
      <p>Quando um bot, um grupo ou a Sora precisar de uma decisão, o pedido aparece aqui.</p>
    </div>}
    {!lista.length && !visiveis.length && !carregado && !erro && <p className="pend-nota" role="status">Carregando pedidos…</p>}
    {!!visiveis.length && <ul className="pend-central" aria-label="Pedidos que esperam você">{visiveis.map(({ pedido, saindo }) => <Pedido key={pedido.id} pedido={pedido} saindo={saindo} aoNavegar={onFechar} />)}</ul>}
  </Modal>;
}

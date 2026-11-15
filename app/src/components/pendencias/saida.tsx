import { CartaoPrecisaDeVoce } from './CartaoPrecisaDeVoce';
import { DURACAO_LINHA, usePedidosComSaida } from './usePedidosComSaida';
import type { PedidoAtencao } from './tipos';

/** Lista de cartões com a linha "✓ …" depois da decisão. */
export function ListaPedidos({ pedidos, className = '', ...cartao }: { pedidos: PedidoAtencao[]; className?: string; compacto?: boolean; semGrupo?: boolean }) {
  const visiveis = usePedidosComSaida(pedidos, DURACAO_LINHA);
  if (!visiveis.length) return null;
  return <div className={`pend-lista ${className}`}>
    {visiveis.map(({ pedido, saindo, rotulo }) => saindo
      ? <p key={pedido.id} className="pend-resolvida" role="status"><span aria-hidden="true">✓</span> {rotulo}</p>
      : <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} {...cartao} />)}
  </div>;
}

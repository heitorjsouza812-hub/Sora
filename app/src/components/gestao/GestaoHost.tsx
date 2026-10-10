// Host único dos diálogos de gestão: qualquer menu "…" chama pedirApagar/pedirRenomear e este host mostra o Modal.
import { DialogoApagar } from './DialogoApagar';
import { DialogoRenomear } from './DialogoRenomear';
import { fecharGestao, usePedidoGestao } from './acoes';

export function GestaoHost() {
  const pedido = usePedidoGestao();
  if (!pedido) return null;
  const alvo = { tipo: pedido.tipo, id: pedido.id };
  return pedido.acao === 'renomear'
    ? <DialogoRenomear key={`r-${pedido.id}`} alvo={alvo} onClose={fecharGestao} />
    : <DialogoApagar key={`a-${pedido.id}`} alvo={alvo} onClose={fecharGestao} />;
}

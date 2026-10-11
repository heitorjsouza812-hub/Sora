// Host único dos diálogos de gestão: qualquer menu "…" chama pedirApagar/pedirRenomear e este host age.
// Apagar: direto com toast "Desfazer"; o Modal só aparece para ações grandes (veja apagar.ts).
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { lerEstado, useProjetos } from '../../state/projetos';
import { DialogoApagar } from './DialogoApagar';
import { DialogoRenomear } from './DialogoRenomear';
import { fecharGestao, usePedidoGestao } from './acoes';
import { apagarComDesfazer, precisaConfirmar } from './apagar';

export function GestaoHost() {
  const pedido = usePedidoGestao();
  const e = useProjetos();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const direto = pedido?.acao === 'apagar' && !precisaConfirmar(pedido, e);

  useEffect(() => {
    if (!pedido || !direto) return;
    const aberto = apagarComDesfazer({ tipo: pedido.tipo, id: pedido.id }, lerEstado(), pathname);
    fecharGestao();
    if (aberto) navigate('/');
  }, [pedido, direto, pathname, navigate]);

  if (!pedido || direto) return null;
  const alvo = { tipo: pedido.tipo, id: pedido.id };
  return pedido.acao === 'renomear'
    ? <DialogoRenomear key={`r-${pedido.id}`} alvo={alvo} onClose={fecharGestao} />
    : <DialogoApagar key={`a-${pedido.id}`} alvo={alvo} onClose={fecharGestao} />;
}

import { useEffect } from 'react';
import { acompanharConversa, carregarMensagens, useProjetos } from '../../state/projetos';
export function HistoricoConversa({ conversaId }: { conversaId?: string }) {
  const e = useProjetos();
  const h = conversaId ? e.historicos?.[conversaId] : undefined;
  useEffect(() => { if (conversaId && !conversaId.startsWith('local-')) { void carregarMensagens(conversaId); acompanharConversa(conversaId); } }, [conversaId]);
  if (!conversaId) return null;
  if (h?.carregando) return <p role="status">Carregando mensagens…</p>;
  if (h?.erro) return <p role="alert">{h.erro} <button onClick={() => void carregarMensagens(conversaId, h.carregado)}>Tentar de novo</button></p>;
  return h?.anteriores ? <button type="button" onClick={() => void carregarMensagens(conversaId, true)}>Carregar anteriores</button> : null;
}

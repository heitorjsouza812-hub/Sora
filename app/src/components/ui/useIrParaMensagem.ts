// Abre a conversa já na mensagem apontada por `#msg-<id>` (vindo da busca da paleta Ctrl+K):
// rola até ela, destaca de leve e, se ainda não foi carregada, pede mais mensagens até achar (com limite).
import { useCallback, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { toast } from '../base';
import { carregarMensagens, lerEstado, useProjetos } from '../../state/projetos';

export const LIMITE_CARGAS = 12;
const DESTAQUE_MS = 2400;

const proximoQuadro = () => new Promise<void>(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
export const idDaAncora = (hash: string): string | null => {
  const bruto = /^#msg-(.+)$/.exec(hash)?.[1];
  if (!bruto) return null;
  try { return decodeURIComponent(bruto); } catch { return bruto; }
};
export const seletorDaMensagem = (id: string) => `[data-msg-id="${CSS.escape(id)}"]`;

/**
 * @param pronto  a primeira carga da conversa terminou (sem isso o hash espera)
 * @param carregarMais  pede mais mensagens; devolve `false` quando não há mais nada a carregar
 */
export function useIrParaMensagem(pronto: boolean, carregarMais: () => Promise<boolean>) {
  const { hash } = useLocation();
  const mais = useRef(carregarMais);
  useEffect(() => { mais.current = carregarMais; });
  useEffect(() => {
    const id = idDaAncora(hash);
    if (!id || !pronto) return;
    let cancelado = false, limpar: ReturnType<typeof setTimeout> | undefined, alvo: Element | null = null;
    void (async () => {
      for (let tentativa = 0; tentativa <= LIMITE_CARGAS; tentativa++) {
        await proximoQuadro();
        if (cancelado) return;
        alvo = document.querySelector(seletorDaMensagem(id));
        if (alvo) break;
        if (tentativa === LIMITE_CARGAS) break;
        let havia = false;
        try { havia = await mais.current(); } catch { havia = false; }
        if (!havia) { await proximoQuadro(); alvo = document.querySelector(seletorDaMensagem(id)); break; }
      }
      if (cancelado) return;
      if (!alvo) { toast({ mensagem: 'Não encontrei essa mensagem na conversa.', tom: 'erro' }); return; }
      const reduzir = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      alvo.scrollIntoView({ block: 'center', behavior: reduzir ? 'auto' : 'smooth' });
      alvo.classList.add('msg-destaque');
      limpar = setTimeout(() => alvo?.classList.remove('msg-destaque'), DESTAQUE_MS);
    })();
    return () => { cancelado = true; clearTimeout(limpar); alvo?.classList.remove('msg-destaque'); };
  }, [hash, pronto]);
}

/** Conversa 1:1 (Sora ou bot): "Carregar anteriores" até achar a mensagem. */
export function useIrParaMensagemDaConversa(conversaId: string | undefined) {
  const estado = useProjetos();
  const carregarMais = useCallback(async () => {
    if (!conversaId || !lerEstado().historicos?.[conversaId]?.anteriores) return false;
    await carregarMensagens(conversaId, true);
    return true;
  }, [conversaId]);
  useIrParaMensagem(!!conversaId && !!estado.historicos?.[conversaId]?.carregado, carregarMais);
}

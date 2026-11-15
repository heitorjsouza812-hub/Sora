import { useEffect, useRef } from 'react';
import { usePrecisaDeVoce } from '../state/atencao';
import { useBots } from '../state/bots';
import { useGrupos } from '../state/grupos';
import { notificarAtencao, tituloAtencao } from './notificacoes';

export function AvisosAtencao({ abrir }: { abrir: (caminho: string) => void }) {
  const { lista, carregado, erro } = usePrecisaDeVoce();
  const bots = useBots();
  const grupos = useGrupos();
  const vistos = useRef<Set<string> | null>(null);
  const sequencia = useRef(0);
  useEffect(() => { tituloAtencao(lista.length); }, [lista.length]);
  useEffect(() => {
    if (!carregado || erro) return;
    if (!vistos.current) { vistos.current = new Set(lista.map(p => p.id)); return; }
    for (const pedido of lista) {
      if (vistos.current.has(pedido.id)) continue;
      vistos.current.add(pedido.id);
      const origem = pedido.grupoId ? grupos.lista.find(g => g.id === pedido.grupoId)?.nome ?? 'Grupo' : bots.find(b => b.id === pedido.botId)?.nome ?? 'Sora';
      const base = pedido.grupoId ? `/grupos/${encodeURIComponent(pedido.grupoId)}` : pedido.botId ? `/bots/${encodeURIComponent(pedido.botId)}` : '/';
      const caminho = `${base}#pedido-${encodeURIComponent(pedido.id)}`;
      notificarAtencao(++sequencia.current, origem, caminho, abrir);
    }
  }, [lista, carregado, erro, bots, grupos.lista, abrir]);
  return null;
}

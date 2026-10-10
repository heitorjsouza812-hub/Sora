// Painel Trabalho "acoplado" à tela: gaveta à direita no desktop; pílula + BottomSheet no celular.
import { useState } from 'react';
import type { CSSProperties } from 'react';
import { estadoAgente, useAgora, useProjetos } from '../../state/projetos';
import { BottomSheet } from '../overlay';
import { useCelular } from '../ui/useMedia';
import { GavetaTrabalho } from './GavetaTrabalho';
import { PainelTrabalho } from './PainelTrabalho';

export interface TrabalhoDockProps {
  agenteIds: string[];
  /** agente selecionado (controlado) */
  agenteId?: string;
  onAgenteChange?: (id: string) => void;
  aberta: boolean;
  onAlternar: (aberta: boolean) => void;
  semSeletor?: boolean;
  /** só no celular: não mostra a pílula (ex.: quando a tela já tem outro atalho) */
  semPilula?: boolean;
}

export function TrabalhoDock({ agenteIds, agenteId, onAgenteChange, aberta, onAlternar, semSeletor, semPilula }: TrabalhoDockProps) {
  const e = useProjetos();
  const agora = useAgora();
  const celular = useCelular();
  const [escolhido, setEscolhido] = useState<string | undefined>();
  const atual = agenteId ?? escolhido;
  const trabalhando = agenteIds.map(id => e.agentes[id]).find(a => a && estadoAgente(e, a.id, agora).status === 'trabalhando');
  const resumo = trabalhando ? `${trabalhando.nome} · ${trabalhando.verbo}…` : undefined;
  const mudar = (id: string) => { setEscolhido(id); onAgenteChange?.(id); };
  const painel = <PainelTrabalho agenteIds={agenteIds} agenteId={atual} onAgenteChange={mudar} semSeletor={semSeletor} />;

  if (celular) {
    return <>
      {!semPilula && agenteIds.length > 0 && (
        <button type="button" className="work-pill" style={trabalhando ? { '--agent': trabalhando.cor } as CSSProperties : undefined}
          onClick={() => onAlternar(true)} aria-haspopup="dialog">
          <i className={`wk-pulse ${trabalhando ? 'is-live' : ''}`} aria-hidden="true" />
          <strong>Trabalho</strong><span>{resumo ?? 'Ver passos dos agentes'}</span>
        </button>
      )}
      <BottomSheet open={aberta} onClose={() => onAlternar(false)} title="Trabalho" description={resumo} className="work-sheet">{painel}</BottomSheet>
    </>;
  }
  return (
    <GavetaTrabalho aberta={aberta} onAlternar={() => onAlternar(!aberta)} corAtiva={trabalhando?.cor} resumo={resumo}>
      {painel}
    </GavetaTrabalho>
  );
}

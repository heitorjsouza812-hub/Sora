// Painel lateral "Editar agente" — abre o mesmo editor do estúdio de qualquer lugar
// (barra lateral, painel Equipe, cabeçalho do chat). Salvar reflete na hora em todo o app.
import { useEffect } from 'react';
import { atualizarAgente, atualizarSora, useProjetos } from '../../state/projetos';
import { EditorAgente } from './EditorAgente';
import './studio.css';

export interface PainelEditarAgenteProps {
  /** id do agente, ou 'sora' para a Sora */
  agenteId: string;
  onFechar: () => void;
}

export function PainelEditarAgente({ agenteId, onFechar }: PainelEditarAgenteProps) {
  const e = useProjetos();
  useEffect(() => {
    const esc = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onFechar(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onFechar]);

  const sora = agenteId === 'sora';
  const ag = sora ? null : e.agentes[agenteId];
  if (!sora && !ag) return null;
  const inicial = sora
    ? { nome: e.sora.nome, cor: e.sora.cor, funcao: 'Agente principal', tipoMovimento: 'gira' as const, ferramentas: [], instrucoes: '' }
    : { id: ag!.id, nome: ag!.nome, funcao: ag!.funcao, cor: ag!.cor, tipoMovimento: ag!.tipoMovimento, ferramentas: ag!.ferramentas, instrucoes: ag!.instrucoes };

  return (
    <div className="st-overlay" onMouseDown={ev => { if (ev.target === ev.currentTarget) onFechar(); }}>
      <div className="st-sheet" role="dialog" aria-modal="true" aria-label={sora ? 'Editar Sora' : `Editar ${ag!.nome}`}>
        <header className="st-sheet-head">
          <h2>{sora ? 'Personalizar a Sora' : 'Editar agente'}</h2>
          <button type="button" className="st-close" onClick={onFechar} aria-label="Fechar">×</button>
        </header>
        <EditorAgente
          key={agenteId}
          variante="painel"
          modo={sora ? 'sora' : 'agente'}
          inicial={inicial}
          coresEmUso={Object.values(e.agentes).filter(a => a.id !== agenteId).map(a => a.cor)}
          onDescartar={onFechar}
          onSalvar={r => {
            if (sora) atualizarSora({ nome: r.nome, cor: r.cor });
            else atualizarAgente(agenteId, { nome: r.nome, funcao: r.funcao, cor: r.cor, tipoMovimento: r.tipoMovimento, ferramentas: r.ferramentas, instrucoes: r.instrucoes });
            onFechar();
          }}
        />
      </div>
    </div>
  );
}

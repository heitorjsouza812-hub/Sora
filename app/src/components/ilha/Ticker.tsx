import type { PassoTrabalho } from '../../types';
import './ilha-partes.css';

const icones: Record<PassoTrabalho['tipo'], string> = {
  prompt: '→',
  pensamento: '✦',
  ferramenta: '⌘',
  handoff: '↗',
  entrega: '◇',
};

function textoDoPasso(passo: PassoTrabalho): string {
  if (passo.tipo === 'ferramenta' && passo.acao) return passo.acao;
  return passo.texto;
}

export function Ticker({ passos, compacto = false }: { passos: PassoTrabalho[]; compacto?: boolean }) {
  const limite = compacto ? 2 : 3;
  const visiveis = passos.slice(-limite);
  if (!visiveis.length) return <p className="ilha-ticker-vazio">Aguardando o primeiro passo…</p>;

  return (
    <ol className={`ilha-ticker${compacto ? ' ilha-ticker--compacto' : ''}`} aria-label="Atividade recente" aria-live="polite">
      {visiveis.map((passo, indice) => {
        const executando = passo.status === 'executando';
        const concluido = passo.status === 'concluido';
        return (
          <li key={passo.id} className={`ilha-ticker__linha ilha-ticker__linha--${passo.status}`} aria-current={executando ? 'step' : undefined}>
            <span className="ilha-ticker__icone" aria-hidden="true">{concluido ? '✓' : icones[passo.tipo]}</span>
            <span className={executando ? 'ilha-shimmer' : undefined}>{textoDoPasso(passo)}</span>
            {!compacto && indice === visiveis.length - 1 && executando && <small>agora</small>}
          </li>
        );
      })}
    </ol>
  );
}

// Peças visuais de uma entrega. Cada POSIÇÃO tem uma composição própria (recorte, filtro e texto
// em Playfair), então nunca aparecem duas peças iguais lado a lado — mesmo que a foto se repita.
// Sem foto, a peça é gerada na cor do agente. Vale para qualquer equipe.
import type { CSSProperties } from 'react';

const COMPOSICOES = [
  { classe: 'post', titulo: 'O novo começa aqui.', detalhe: 'Lançamento' },
  { classe: 'story', titulo: 'Sua nova pausa favorita.', detalhe: 'Vem aí' },
  { classe: 'poster', titulo: 'Abrimos!', detalhe: 'Já disponível' },
  { classe: 'detail', titulo: 'Bora conferir?', detalhe: 'Novidade' },
] as const;

export interface PecaProps {
  /** posição da peça na entrega (define a composição) */
  indice: number;
  imagem?: string;
  /** cor do agente (fundo das peças geradas) */
  cor: string;
  /** marca/assunto exibido no topo (ex.: "Cafeteria") */
  marca?: string;
  /** miniatura: só a composição visual, sem texto */
  compacta?: boolean;
  gerando?: boolean;
  className?: string;
}

export function PecaCampanha({ indice, imagem, cor, marca = '', compacta = false, gerando = false, className = '' }: PecaProps) {
  const c = COMPOSICOES[indice % COMPOSICOES.length];
  return (
    <div className={`campaign-piece campaign-piece-${c.classe} campaign-piece-index-${indice % COMPOSICOES.length} ${imagem ? '' : 'campaign-piece-generated'} ${gerando ? 'is-generating' : ''} ${className}`}
      style={{ '--agent': cor } as CSSProperties} role="img" aria-label={`Peça ${indice + 1}: ${c.titulo}`}>
      {imagem && <img src={imagem} alt="" />}
      <span className="campaign-piece-shade" />
      {!compacta && (
        <div className="campaign-piece-copy" aria-hidden="true">
          {marca && <small>{marca.toUpperCase()}</small>}
          <strong>{c.titulo}</strong>
          <span>{c.detalhe}</span>
        </div>
      )}
    </div>
  );
}

// Estados vazios da grade (item 48): sem projetos → a Sora em idle + modelos prontos clicáveis
// (preenchem o compositor); busca/filtro sem resultado → botão para limpar.
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import { MODELOS_PROJETO, type ModeloProjeto } from './modelos';

export interface EstadoVazioProps {
  corSora: string;
  nomeSora: string;
  busca?: boolean;
  onLimpar?: () => void;
  onModelo?: (modelo: ModeloProjeto) => void;
}

export function EstadoVazio({ corSora, nomeSora, busca, onLimpar, onModelo }: EstadoVazioProps) {
  if (busca) {
    return (
      <div className="pj-vazio">
        <SoraOrb size={96} color={corSora} state="idle" seed={5} decorative />
        <h3>Nenhum projeto encontrado</h3>
        <p>Tente outra palavra ou outro filtro.</p>
        {onLimpar && <Button className="pj-vazio__acao" onClick={onLimpar}>Limpar busca e filtro</Button>}
      </div>
    );
  }
  return (
    <div className="pj-vazio">
      <SoraOrb size={120} color={corSora} state="idle" seed={5} decorative />
      <h3>Nenhum projeto ainda</h3>
      <p>Comece por um modelo pronto ou descreva o seu. A {nomeSora} monta o plano, cria a equipe e te avisa quando estiver pronto para revisar.</p>
      {onModelo && (
        <ul className="pj-modelos" aria-label="Modelos de projeto">
          {MODELOS_PROJETO.map((m) => (
            <li key={m.id}>
              <button type="button" className="pj-modelo" onClick={() => onModelo(m)}>
                <strong>{m.rotulo}</strong>
                <span>{m.descricao}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

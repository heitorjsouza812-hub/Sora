import type { PropostaInstrucoes } from './proposta';

/** Mostra o texto novo (e a diferença) que o bot propõe para as próprias instruções, antes de aprovar. */
export function ProporInstrucoes({ proposta }: { proposta: PropostaInstrucoes }) {
  return (
    <div className="pend-proposta" data-proposta="instrucoes">
      {proposta.motivo && <p className="pend-dano"><b>Motivo:</b> {proposta.motivo}</p>}
      <p className="pend-dano"><b>Instruções propostas:</b></p>
      <pre className="pend-proposta-texto" tabIndex={0} aria-label="Instruções propostas">{proposta.instrucoes}</pre>
      {proposta.diferenca && <details className="pend-proposta-dif">
        <summary>Ver o que mudou</summary>
        <pre className="pend-proposta-texto" tabIndex={0} aria-label="O que mudou">{proposta.diferenca}</pre>
      </details>}
    </div>
  );
}

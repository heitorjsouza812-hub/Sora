/** Botão redondo "ir para o fim" (36 px, só a seta); com mensagens novas ganha um ponto de 8 px. */
export function IrParaFim({ novas, onClick }: { novas: number; onClick: () => void }) {
  return (
    <button type="button" className="ir-fim" onClick={onClick} aria-label={novas ? `Ir para o fim: ${novas} ${novas === 1 ? 'mensagem nova' : 'mensagens novas'}` : 'Ir para o fim'}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
      {novas > 0 && <i className="ir-fim-novas" aria-hidden="true" />}
    </button>
  );
}

/** Botão flutuante "ir para o fim" (com contador de mensagens novas). */
export function IrParaFim({ novas, onClick }: { novas: number; onClick: () => void }) {
  return (
    <button type="button" className="ir-fim" onClick={onClick} aria-label={novas ? `Ir para o fim: ${novas} ${novas === 1 ? 'mensagem nova' : 'mensagens novas'}` : 'Ir para o fim'}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
      {novas > 0 ? <>Novas <b>{novas}</b></> : 'Ir para o fim'}
    </button>
  );
}

// Chip "Guardei isto" com Desfazer: aparece quando o bot guarda uma memória nova (evento SSE memoria.criada).
// Uso: <AvisosMemoria agenteId={bot.id} /> perto do fim da conversa daquele bot.
import { useState } from 'react';
import { apagarMemoria, dispensarAvisoMemoria, useAvisosMemoria } from '../../state/pecas';
import { mensagemDeErro } from '../../api/cliente';
import './memoria.css';

export function AvisosMemoria({ agenteId }: { agenteId: string }) {
  const avisos = useAvisosMemoria(agenteId);
  const [erro, setErro] = useState<string | null>(null);
  if (!avisos.length) return null;
  const desfazer = async (id: string) => {
    try { await apagarMemoria(id); dispensarAvisoMemoria(id); setErro(null); } catch (e) { setErro(mensagemDeErro(e)); }
  };
  return <div className="mem-avisos" role="status" aria-live="polite">
    {avisos.map(a => <div key={a.memoriaId} className="mem-aviso">
      <span className="mem-aviso__rotulo">Guardei isto</span>
      <span className="mem-aviso__texto">{a.texto}</span>
      <button type="button" onClick={() => void desfazer(a.memoriaId)}>Desfazer</button>
      <button type="button" className="mem-aviso__fechar" aria-label="Dispensar aviso" onClick={() => dispensarAvisoMemoria(a.memoriaId)}>×</button>
    </div>)}
    {erro && <p className="mem-erro" role="alert">{erro}</p>}
  </div>;
}

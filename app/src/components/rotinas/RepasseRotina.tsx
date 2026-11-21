// "Depois, passar o resultado para…" (Onda 3): quando a rotina termina com resultado, outro bot
// recebe esse resultado e faz a parte dele, também sem ninguém olhando. Só um salto.
import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { alterarRotina, type Rotina } from '../../state/pecas';
import { useBots } from '../../state/bots';
import './rotinas.css';

export function RepasseRotina({ rotina, aoMudar }: { rotina: Rotina; aoMudar: (r: Rotina) => void }) {
  const bots = useBots().filter(b => b.id !== rotina.agente_id);
  const [editando, setEditando] = useState(false);
  const [bot, setBot] = useState(rotina.seguinte_agente_id ?? '');
  const [pedido, setPedido] = useState(rotina.seguinte_pedido ?? '');
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const atual = rotina.seguinte_agente_id ? bots.find(b => b.id === rotina.seguinte_agente_id) : undefined;

  const salvar = async (mudanca: Parameters<typeof alterarRotina>[1]) => {
    setOcupado(true); setAviso(null);
    try { aoMudar(await alterarRotina(rotina.id, mudanca)); setEditando(false); }
    catch (e) { setAviso(mensagemDeErro(e)); }
    finally { setOcupado(false); }
  };
  const abrir = () => { setBot(rotina.seguinte_agente_id ?? bots[0]?.id ?? ''); setPedido(rotina.seguinte_pedido ?? ''); setEditando(true); };

  return <section className="gancho repasse" aria-label="Passar o resultado para outro bot">
    <p className="gancho-titulo"><strong>Depois desta rotina</strong></p>
    {editando ? <form className="repasse-form" onSubmit={e => { e.preventDefault(); void salvar({ seguinte_agente_id: bot, seguinte_pedido: pedido.trim() }); }}>
      <label className="gancho-campo"><span>Passar o resultado para</span>
        <select value={bot} onChange={e => setBot(e.target.value)} required>
          {bots.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}
        </select></label>
      <label className="gancho-campo"><span>O que ele faz com o resultado</span>
        <textarea rows={2} maxLength={2000} value={pedido} onChange={e => setPedido(e.target.value)} placeholder="ex.: Escreva um post curto para o Instagram com isso." /></label>
      <div className="mem-acoes">
        <button type="button" disabled={ocupado} onClick={() => setEditando(false)}>Cancelar</button>
        <button type="submit" disabled={ocupado || !bot || !pedido.trim()}>Salvar</button>
      </div>
    </form> : rotina.seguinte_agente_id ? <>
      <small>O resultado segue para <b>{atual?.nome ?? 'um bot que não existe mais'}</b>: “{rotina.seguinte_pedido}”. Ele também trabalha sem ninguém olhando e responde na conversa dele.</small>
      <div className="mem-acoes">
        <button type="button" disabled={ocupado} onClick={abrir}>Mudar</button>
        <button type="button" disabled={ocupado} onClick={() => void salvar({ seguinte_agente_id: null })}>Não passar adiante</button>
      </div>
    </> : <>
      <small>O resultado pode seguir para outro bot, que faz a parte dele (ex.: um junta as notícias, o outro escreve o post).</small>
      <div className="mem-acoes">
        <button type="button" disabled={ocupado || bots.length === 0} onClick={abrir}>Passar o resultado para outro bot</button>
      </div>
      {bots.length === 0 && <small>Crie outro bot para usar isto.</small>}
    </>}
    {aviso && <p className="mem-erro" role="alert">{aviso}</p>}
  </section>;
}

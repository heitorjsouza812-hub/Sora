import { useState, type CSSProperties, type FormEvent } from 'react';
import { SoraOrb } from '../mascot';
import type { RascunhoConstrutor } from './types';

interface TesteMsg { id: string; autor: 'agente' | 'usuario'; texto: string }
export function AgentPreview({ agente }: { agente: RascunhoConstrutor }) {
  const funcaoEspecifica = agente.funcao.trim() && agente.funcao.trim().toLowerCase() !== 'assistente';
  const apresentacao = agente.descricaoCurta || (funcaoEspecifica ? `Posso ajudar com ${agente.funcao.toLowerCase()}.` : 'Estou pronto para ajudar no que você precisar.');
  const boasVindas = `Oi! Sou ${agente.nome || 'seu novo agente'}. ${apresentacao}`;
  const [mensagens, setMensagens] = useState<TesteMsg[]>([{ id: 'welcome', autor: 'agente', texto: boasVindas }]);
  const [texto, setTexto] = useState('');
  const [pensando, setPensando] = useState(false);
  const enviar = (event: FormEvent) => { event.preventDefault(); const valor = texto.trim(); if (!valor || pensando) return; setTexto(''); setMensagens(x => [...x, { id: crypto.randomUUID(), autor: 'usuario', texto: valor }]); setPensando(true); window.setTimeout(() => { const regra = agente.instrucoes.split(/[.!?]/)[0]?.trim(); setMensagens(x => [...x, { id: crypto.randomUUID(), autor: 'agente', texto: `${agente.tom === 'amigavel' ? 'Claro! ' : ''}Vou cuidar de ${valor.toLowerCase()}${regra ? ` seguindo esta orientação: ${regra.toLowerCase()}` : ''}. Esta é uma resposta simulada para você testar o comportamento.` }]); setPensando(false); }, 700); };
  const reiniciar = () => { setMensagens([{ id: crypto.randomUUID(), autor: 'agente', texto: boasVindas }]); setPensando(false); };
  return <section className="bld-preview" style={{ '--agent': agente.cor } as CSSProperties}>
    <header><span>Prévia</span><button type="button" onClick={reiniciar}>Reiniciar teste</button></header>
    <div className="bld-preview-profile"><SoraOrb size={150} color={agente.cor} state={pensando ? 'thinking' : 'working'} movimento={agente.tipoMovimento} seed={25} title={`Orb de ${agente.nome}`} /><strong>{agente.nome || 'Sem nome'}</strong><small>{agente.funcao || 'Função do agente'}</small></div>
    <div className="bld-test-chat" aria-live="polite">{mensagens.map(m => <p key={m.id} className={`bld-test-${m.autor}`}>{m.texto}</p>)}{pensando && <div className="bld-test-thinking"><SoraOrb size={34} color={agente.cor} state="thinking" movimento={agente.tipoMovimento} seed={26} decorative /><span>Pensando…</span></div>}</div>
    {agente.frasesIniciais[0] && mensagens.length === 1 && <button className="bld-starter" type="button" onClick={() => setTexto(agente.frasesIniciais[0])}>{agente.frasesIniciais[0]}</button>}
    <form className="bld-test-compose" onSubmit={enviar}><input value={texto} onChange={e => setTexto(e.target.value)} placeholder={`Mensagem para ${agente.nome || 'o agente'}…`} /><button type="submit" disabled={!texto.trim() || pensando}>↑</button></form>
  </section>;
}


import { useState, type CSSProperties, type FormEvent } from 'react';
import { enviarParaAgente, gerandoNa, mensagensDa, useAgora, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import type { RascunhoConstrutor } from './types';

export function AgentPreview({ agente }: { agente: RascunhoConstrutor }) {
  const estado = useProjetos();
  const agora = useAgora();
  const mensagens = agente.id ? mensagensDa(estado, agente.id, agora) : [];
  const pensando = agente.id ? gerandoNa(estado, agente.id, agora) : false;
  const [texto, setTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const enviar = (event: FormEvent) => {
    event.preventDefault();
    const valor = texto.trim();
    if (!agente.id || !valor || pensando || enviando) return;
    setTexto(''); setErro(''); setEnviando(true);
    void enviarParaAgente(agente.id, valor).catch(e => {
      setTexto(valor);
      setErro(e instanceof Error ? e.message : 'Não foi possível enviar. Tente de novo.');
    }).finally(() => setEnviando(false));
  };
  return <section className="bld-preview" style={{ '--agent': agente.cor } as CSSProperties}>
    <header><span>Prévia</span><small>{agente.id ? 'Conversa real' : 'Rascunho'}</small></header>
    <div className="bld-preview-profile"><SoraOrb size={150} color={agente.cor} state={pensando ? 'thinking' : 'working'} movimento={agente.tipoMovimento} seed={25} title={`Orb de ${agente.nome}`} /><strong>{agente.nome || 'Sem nome'}</strong><small>{agente.funcao || 'Função do agente'}</small></div>
    <div className="bld-test-chat" aria-live="polite">
      {!agente.id && <p className="bld-test-aviso">Salve o agente para testar em uma conversa real.</p>}
      {agente.id && !mensagens.length && <p className="bld-test-aviso">Envie uma mensagem para iniciar a conversa real com este agente.</p>}
      {mensagens.map(m => <p key={m.id} className={`bld-test-${m.autor === 'usuario' ? 'usuario' : 'agente'}`}>{m.texto}</p>)}
      {pensando && <div className="bld-test-thinking"><SoraOrb size={34} color={agente.cor} state="thinking" movimento={agente.tipoMovimento} seed={26} decorative /><span>Pensando…</span></div>}
    </div>
    {agente.frasesIniciais[0] && mensagens.length === 1 && <button className="bld-starter" type="button" onClick={() => setTexto(agente.frasesIniciais[0])}>{agente.frasesIniciais[0]}</button>}
    {erro && <p className="bld-test-erro" role="alert">{erro}</p>}
    <form className="bld-test-compose" onSubmit={enviar}><input value={texto} onChange={e => setTexto(e.target.value)} disabled={!agente.id || enviando} placeholder={agente.id ? `Mensagem para ${agente.nome || 'o agente'}…` : 'Salve o agente para testar…'} aria-label={agente.id ? `Mensagem para ${agente.nome || 'o agente'}` : 'Teste indisponível antes de salvar'} /><button type="submit" aria-label="Enviar mensagem" disabled={!agente.id || !texto.trim() || pensando || enviando}>↑</button></form>
  </section>;
}


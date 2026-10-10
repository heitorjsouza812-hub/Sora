import { useRef, useState, type FormEvent } from 'react';
import { agenteDeDescricao, PALETA_AGENTES, verboPara } from '../../data/planejador';
import { SoraOrb } from '../mascot';
import type { MensagemConstrutor, RascunhoConstrutor } from './types';

export interface CreateConversationProps { rascunho: RascunhoConstrutor; onChange: (valor: RascunhoConstrutor) => void }

export function CreateConversation({ rascunho, onChange }: CreateConversationProps) {
  const [mensagens, setMensagens] = useState<MensagemConstrutor[]>([{ id: 'inicio', autor: 'sora', texto: 'O que este agente deve fazer? Conte como se estivesse explicando para uma pessoa nova na equipe.' }]);
  const [texto, setTexto] = useState('');
  const [etapa, setEtapa] = useState(0);
  const [pensando, setPensando] = useState(false);
  const timer = useRef(0);
  const responder = (fala: string, patch: Partial<RascunhoConstrutor>, proxima: number) => {
    setPensando(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { onChange({ ...rascunho, ...patch }); setMensagens(x => [...x, { id: crypto.randomUUID(), autor: 'sora', texto: fala }]); setEtapa(proxima); setPensando(false); }, 650);
  };
  const enviar = (event: FormEvent) => {
    event.preventDefault(); const valor = texto.trim(); if (!valor || pensando) return;
    setMensagens(x => [...x, { id: crypto.randomUUID(), autor: 'usuario', texto: valor }]); setTexto('');
    if (etapa === 0) {
      const gerado = agenteDeDescricao(valor);
      responder(`Entendi. Sugiro o nome ${gerado.nome} para um agente de ${gerado.funcao.toLowerCase()}. Você pode trocar o nome agora ou seguir com ele.`, { ...gerado, descricaoCurta: valor.slice(0, 90), frasesIniciais: [`Me ajude com ${gerado.funcao.toLowerCase()}`] }, 1);
    } else if (etapa === 1) responder(`Perfeito, vou chamá-lo de ${valor}. Agora escolha uma cor e um jeito de se mover.`, { nome: valor.slice(0, 24) }, 2);
    else if (etapa === 3) responder('Ferramentas anotadas. Por fim, descreva qualquer regra, limite ou preferência importante.', { ferramentas: valor.split(/,| e /).map(x => x.trim()).filter(Boolean).slice(0, 6) }, 4);
    else responder(`Pronto. Organizei as instruções e o agente ficará ${verboPara(rascunho.funcao).toLowerCase()} quando trabalhar. Você pode testar na prévia ou ajustar tudo em Configurar.`, { instrucoes: valor }, 5);
  };
  const escolherAparencia = (cor: string, movimento: RascunhoConstrutor['tipoMovimento']) => {
    onChange({ ...rascunho, cor, tipoMovimento: movimento });
    setMensagens(x => [...x, { id: crypto.randomUUID(), autor: 'usuario', texto: `Cor ${cor} e movimento ${movimento}.` }, { id: crypto.randomUUID(), autor: 'sora', texto: 'Boa escolha. Quais ferramentas ele deve poder usar? Separe por vírgulas.' }]); setEtapa(3);
  };
  return <section className="bld-create" aria-label="Conversa de criação">
    <div className="bld-thread" aria-live="polite">{mensagens.map(m => <div key={m.id} className={`bld-message bld-message-${m.autor}`}>{m.autor === 'sora' && <SoraOrb size={34} state="idle" seed={11} decorative />}<p>{m.texto}</p></div>)}
      {pensando && <div className="bld-message bld-message-sora"><SoraOrb size={42} state="thinking" seed={12} title="Sora está pensando" /><p className="bld-shimmer">Pensando no seu agente…</p></div>}
      {etapa === 2 && !pensando && <div className="bld-inline-choices"><span>Cores</span><div>{PALETA_AGENTES.slice(0, 8).map(c => <button key={c} type="button" className="bld-color-chip" style={{ '--choice': c } as React.CSSProperties} aria-label={`Escolher cor ${c}`} onClick={() => escolherAparencia(c, rascunho.tipoMovimento)} />)}</div><span>Movimento</span><div>{(['gira', 'vibracao', 'espiral', 'ondas'] as const).map(m => <button type="button" key={m} onClick={() => escolherAparencia(rascunho.cor, m)}>{m === 'vibracao' ? 'Vibração' : m[0].toUpperCase() + m.slice(1)}</button>)}</div></div>}
    </div>
    <form className="bld-compose" onSubmit={enviar}><textarea value={texto} onChange={e => setTexto(e.target.value)} placeholder={etapa === 0 ? 'Ex.: pesquisa concorrentes e resume as melhores ideias…' : etapa === 1 ? `Use ${rascunho.nome} ou escreva outro nome…` : etapa === 3 ? 'Ex.: Perplexity, Notion, Google Drive' : 'Escreva instruções e limites…'} rows={2} /><button type="submit" disabled={!texto.trim() || pensando} aria-label="Enviar">↑</button></form>
  </section>;
}


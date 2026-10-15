// /celular — a mesma conta e o mesmo projeto, por voz. Sem projeto: só a Sora, esperando.
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { VoiceBeam } from 'voice-glow';
import { statusDaSora } from '../components/layout/useSoraStatus';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { MicIcon } from '../components/ui/Icons';
import { ShimmerText } from '../components/ui/ShimmerText';
import { VOICE } from '../data/voiceLevel';
import {
  agentesDoProjeto, conversarComSora, estadoAgente, estadoProjeto, lerEstado, mensagensDa, projetoAtivo, useAgora, useProjetos,
} from '../state/projetos';

const PEDIDO_VOZ = 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.';
const AJUSTE_VOZ = 'Deixe os textos mais descontraídos.';

export default function Mobile() {
  const e = useProjetos();
  const agora = useAgora();
  const p = projetoAtivo(e);
  const ep = p ? estadoProjeto(e, p, agora) : null;
  const sora = statusDaSora(e, agora);
  const ags = agentesDoProjeto(e, p, agora);
  const [ouvindo, setOuvindo] = useState(false);
  const timer = useRef(0);
  const processando = !!ep && ['pensando', 'planejando', 'coordenando'].includes(ep.fase);
  const msgs = p ? mensagensDa(e, `sora:${p.id}`, agora).slice(-4) : [];
  const alvo = p?.ajusteAgenteId ? e.agentes[p.ajusteAgenteId] : undefined;
  const novaPronta = msgs.some(m => m.texto === 'Pronto. Veja a nova versão.');

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const falar = () => {
    if (ouvindo) {
      window.clearTimeout(timer.current);
      setOuvindo(false);
      conversarComSora(p ? AJUSTE_VOZ : PEDIDO_VOZ);
      return;
    }
    setOuvindo(true);
    timer.current = window.setTimeout(() => { setOuvindo(false); conversarComSora(projetoAtivo(lerEstado()) ? AJUSTE_VOZ : PEDIDO_VOZ); }, 3200);
  };
  const level = () => ouvindo ? VOICE.levels[Math.floor(Date.now() / (1000 / VOICE.fps)) % VOICE.levels.length] : 0;

  return <main className="mobile-screen">
    <header className="mobile-header">
      <SoraOrb size={42} color={e.sora.cor} state={ouvindo ? 'listening' : sora.orb} pulseKey={sora.pulso} glow={false} decorative />
      <span><strong>{e.sora.nome}</strong><small role="status">{ouvindo ? 'Ouvindo…' : p ? `${p.titulo} · ${sora.rotulo}` : 'Disponível'}</small></span>
      <Link className="share-button mobile-back" to="/">Desktop</Link>
    </header>
    <div className="mobile-content">
      {!p && (
        <div className="mobile-empty">
          <SoraOrb size={150} color={e.sora.cor} state={ouvindo ? 'listening' : 'idle'} lookAt={ouvindo ? { x: 0, y: .8 } : null} title={e.sora.nome} />
          <h1>Fale com a {e.sora.nome}</h1>
          <p>Toque no microfone e descreva o que você precisa. A {e.sora.nome} monta a equipe.</p>
        </div>
      )}
      {p && <>
        <section className="mobile-team card" aria-label="Equipe">
          <p className="eyebrow">Equipe</p>
          {!ags.length && <SoraThinking size={28} color={e.sora.cor} label="Montando a equipe…" />}
          <div>{ags.map(a => {
            const st = estadoAgente(e, a.id, agora);
            return <Link to={`/chat/${a.id}`} key={a.id} style={{ '--agent': a.cor } as CSSProperties}>
              <span className="mobile-orb"><SoraOrb size={38} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative
                state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : 'idle'} />{st.status === 'concluido' && <i aria-hidden="true">✓</i>}</span>
              <b className="agent-color">{a.nome}</b><small>{st.rotulo}</small>
            </Link>;
          })}</div>
        </section>
        {(ep?.fase === 'pronto' || ep?.fase === 'aprovado' || p.versao > 1) && (
          <section className="mobile-campaign card"><h2>{p.titulo}</h2>
            <ul>{p.agenteIds.map(id => e.agentes[id] && p.entregas[id] && <li key={id} style={{ '--agent': e.agentes[id].cor } as CSSProperties}><b className="agent-color">{p.entregas[id].titulo}</b> · {p.entregas[id].resumo}</li>)}</ul>
            <Link to={`/revisao/${p.id}`} className="mobile-review">Revisar</Link>
          </section>
        )}
        {msgs.map(m => m.autor === 'usuario'
          ? <div className="mobile-user-message" key={m.id}>{m.texto}</div>
          : <div className="mobile-status" key={m.id}><SoraOrb size={26} color={e.sora.cor} state="done" glow={false} decorative /><span>{m.texto}</span></div>)}
        {processando && <div className="mobile-status" role="status"><SoraThinking size={26} color={e.sora.cor} label={p.versao > 1 ? `${e.sora.nome} está ajustando…` : `${e.sora.nome} está trabalhando…`} /></div>}
        {novaPronta && alvo && p.entregasAnteriores?.[alvo.id] && <>
          <section className="mobile-caption old-version card"><p className="eyebrow">Versão anterior</p><p>{p.entregasAnteriores[alvo.id].resumo}</p></section>
          <section className="mobile-caption new-version card"><span>Nova versão</span><p>{p.entregas[alvo.id]?.itens?.slice(-1)[0] ?? p.entregas[alvo.id]?.resumo}</p></section>
        </>}
      </>}
    </div>
    <div className="mobile-composer-wrap">
      <VoiceBeam type="mobile" level={level} active={ouvindo || processando} theme="dark" strength={.85}>
        <div className="mobile-composer">
          <span>{ouvindo ? <ShimmerText>Ouvindo…</ShimmerText> : processando ? <ShimmerText>{`${e.sora.nome} está trabalhando…`}</ShimmerText> : `Mensagem para ${e.sora.nome}…`}</span>
          <button type="button" className={ouvindo ? 'is-live' : ''} onClick={falar} aria-label={ouvindo ? 'Parar de ouvir e enviar' : `Falar com a ${e.sora.nome}`} aria-pressed={ouvindo}><MicIcon /></button>
        </div>
      </VoiceBeam>
    </div>
  </main>;
}

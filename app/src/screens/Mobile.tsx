import { useEffect, useState } from 'react';
import { VoiceBeam } from 'voice-glow';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { CampaignPiece } from '../components/ui/CampaignPiece';
import { MicIcon } from '../components/ui/Icons';
import { ShimmerText } from '../components/ui/ShimmerText';
import { agentes, legendaAnterior, legendaNova, pecas, PEDIDO_AJUSTE } from '../data/mock';
import { VOICE } from '../data/voiceLevel';

type MobileStage = 'idle' | 'listening' | 'processing' | 'ready';

export default function Mobile() {
  const [stage, setStage] = useState<MobileStage>('idle');
  useEffect(() => {
    if (stage !== 'listening') return;
    const processing = window.setTimeout(() => setStage('processing'), 3200);
    return () => window.clearTimeout(processing);
  }, [stage]);
  useEffect(() => {
    if (stage !== 'processing') return;
    const ready = window.setTimeout(() => setStage('ready'), 3600);
    return () => window.clearTimeout(ready);
  }, [stage]);

  const level = () => stage === 'listening' ? VOICE.levels[Math.floor(Date.now() / (1000 / VOICE.fps)) % VOICE.levels.length] : 0;
  return <main className="mobile-screen">
    <header className="mobile-header"><SoraOrb size={42} state={stage === 'processing' ? 'thinking' : stage === 'ready' ? 'done' : 'idle'} glow={false} /><span><strong>Sora</strong><small>{stage === 'ready' ? 'Ajuste concluído' : 'Campanha em andamento'}</small></span></header>
    <div className="mobile-content">
      <section className="mobile-team card"><p className="eyebrow">Equipe</p><div>{agentes.map((agente) => <span key={agente.id}><span className="mobile-orb"><SoraOrb size={38} color={agente.cor} movimento={agente.tipoMovimento} state="done" glow={false} /><i>✓</i></span><b style={{ color: agente.cor }}>{agente.nome}</b></span>)}</div></section>
      <section className="mobile-campaign card"><h2>Campanha da cafeteria</h2><div>{pecas.map((peca) => <CampaignPiece piece={peca} key={peca.titulo} />)}</div><p>12 posts no calendário</p></section>
      <section className={`mobile-caption card ${stage === 'ready' ? 'old-version' : ''}`}><p className="eyebrow">Legenda · Post de inauguração</p><p>{legendaAnterior}</p>{stage === 'ready' && <small>Versão anterior</small>}</section>
      {stage !== 'idle' && <div className="mobile-user-message">🎙 {PEDIDO_AJUSTE}</div>}
      {stage === 'processing' && <div className="mobile-status"><SoraThinking size={26} label="Sora está ajustando…" /></div>}
      {stage === 'ready' && <><div className="mobile-status"><SoraOrb size={26} state="done" glow={false} /><span>Pronto. Veja a nova versão.</span></div><section className="mobile-caption new-version card"><span>Nova versão</span><p>{legendaNova}</p></section></>}
    </div>
    <div className="mobile-composer-wrap">
      <VoiceBeam type="mobile" level={level} active={stage === 'listening' || stage === 'processing'} theme="dark" strength={.85}>
        <div className="mobile-composer">
          <span>{stage === 'listening' ? <ShimmerText>Ouvindo…</ShimmerText> : stage === 'processing' ? <ShimmerText>Sora está ajustando…</ShimmerText> : 'Mensagem para Sora…'}</span>
          <button className={stage === 'listening' ? 'is-live' : ''} onClick={() => setStage(stage === 'listening' ? 'processing' : 'listening')} aria-label={stage === 'listening' ? 'Parar de ouvir' : 'Falar com a Sora'} aria-pressed={stage === 'listening'}><MicIcon /></button>
        </div>
      </VoiceBeam>
    </div>
  </main>;
}


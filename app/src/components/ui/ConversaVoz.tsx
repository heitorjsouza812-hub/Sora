import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, mensagemDeErro } from '../../api/cliente';
import { MSG_SEM_VOZ, sintetizarFala, transcreverAudio } from '../../api/voz';
import { enviarParaAgente, gerandoNa, lerEstado, mensagensDa, pararConversa, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import type { Movimento } from '../../types';

type Fase = 'inativo' | 'preparando' | 'ouvindo' | 'transcrevendo' | 'aguardando' | 'falando';
const rotulos: Record<Fase, string> = { inativo: '', preparando: 'Preparando voz…', ouvindo: 'Ouvindo…', transcrevendo: 'Transcrevendo…', aguardando: 'Pensando…', falando: 'Falando…' };

/** Avisos escritos aqui já estão em PT-BR e vão como estão para a tela (`mensagemDeErro` os trocaria pelo texto genérico). */
class AvisoVoz extends Error {}
function textoDoErro(falha: unknown): string {
  if (falha instanceof AvisoVoz) return falha.message;
  const nome = (falha as { name?: string } | null)?.name;
  if (nome === 'NotAllowedError' || nome === 'SecurityError') return 'Permita o uso do microfone no navegador para conversar por voz.';
  if (nome === 'NotFoundError' || nome === 'OverconstrainedError') return 'Não encontrei um microfone neste aparelho.';
  return mensagemDeErro(falha);
}

/** Sessão com recursos próprios: nunca grava enquanto reproduz a resposta. */
export function ConversaVoz({ agenteId, cor, movimento, faixa }: { agenteId: string; cor: string; movimento: Movimento; /** contêiner (acima do compositor) onde aparece o estado da conversa por voz */ faixa?: HTMLElement | null }) {
  const estado = useProjetos();
  const [fase, setFase] = useState<Fase>('inativo');
  const [erro, setErro] = useState('');
  const sessao = useRef<AbortController | null>(null);
  const limparMicrofone = useRef<() => void>(() => {});
  const limparAudio = useRef<() => void>(() => {});
  const anteriores = useRef(new Set<string>());
  const prazo = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const ativo = (ac: AbortController) => sessao.current === ac && !ac.signal.aborted;
  const encerrar = () => {
    sessao.current?.abort(); sessao.current = null;
    limparMicrofone.current(); limparAudio.current(); clearTimeout(prazo.current);
    setFase('inativo');
  };
  const falhou = (falha: unknown, ac: AbortController) => { if (ativo(ac)) { encerrar(); setErro(textoDoErro(falha)); } };

  const ouvir = async (ac: AbortController) => {
    if (!ativo(ac)) return;
    limparAudio.current();
    setFase('ouvindo');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!ativo(ac)) { stream.getTracks().forEach(t => t.stop()); return; }
      const contexto = new AudioContext();
      const fonte = contexto.createMediaStreamSource(stream);
      const medidor = contexto.createAnalyser(); medidor.fftSize = 2048; fonte.connect(medidor);
      const tipo = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
      let gravador: MediaRecorder;
      try { gravador = new MediaRecorder(stream, tipo ? { mimeType: tipo } : undefined); }
      catch (falha) { stream.getTracks().forEach(t => t.stop()); void contexto.close(); throw falha; }
      const partes: Blob[] = [];
      const dados = new Float32Array(medidor.fftSize);
      // Este trecho roda apenas depois do clique e da concessão do microfone, nunca no render.
      // oxlint-disable-next-line react/purity
      let falou = false, ultimaFala = performance.now();
      // oxlint-disable-next-line react/purity
      const inicio = performance.now();
      let timer: ReturnType<typeof setInterval>;
      const liberar = () => { clearInterval(timer); stream.getTracks().forEach(t => t.stop()); fonte.disconnect(); void contexto.close(); };
      limparMicrofone.current = () => { gravador.onstop = null; if (gravador.state !== 'inactive') gravador.stop(); liberar(); };
      gravador.ondataavailable = ev => { if (ev.data.size) partes.push(ev.data); };
      gravador.onerror = () => falhou(new AvisoVoz('Não foi possível gravar o microfone.'), ac);
      gravador.onstop = () => {
        liberar(); limparMicrofone.current = () => {};
        if (!ativo(ac)) return;
        if (!falou) { encerrar(); setErro('Não ouvi nada. Inicie a conversa por voz novamente.'); return; }
        setFase('transcrevendo');
        void transcreverAudio(new Blob(partes, { type: gravador.mimeType }), 'pt', ac.signal).then(async texto => {
          if (!ativo(ac)) return;
          if (!texto) { await ouvir(ac); return; }
          anteriores.current = new Set(mensagensDa(lerEstado(), agenteId, 0).map(m => m.id));
          setFase('aguardando');
          prazo.current = setTimeout(() => falhou(new AvisoVoz('A resposta está demorando. Continue pelo chat.'), ac), 120_000);
          await enviarParaAgente(agenteId, texto);
          if (ativo(ac) && mensagensDa(lerEstado(), agenteId, 0).some(m => !anteriores.current.has(m.id) && m.envio === 'erro')) throw new AvisoVoz('Não foi possível enviar sua fala. Tente novamente no chat.');
        }).catch(falha => falhou(falha, ac));
      };
      gravador.start();
      timer = setInterval(() => {
        medidor.getFloatTimeDomainData(dados);
        const nivel = Math.sqrt(dados.reduce((soma, x) => soma + x * x, 0) / dados.length);
        if (nivel > .018) { falou = true; ultimaFala = performance.now(); }
        if (falou && performance.now() - ultimaFala >= 1500 || performance.now() - inicio > 60_000) {
          clearInterval(timer); if (gravador.state !== 'inactive') gravador.stop();
        }
      }, 50);
    } catch (falha) { falhou(falha, ac); }
  };

  const iniciar = async () => {
    if (sessao.current) return;
    const ac = new AbortController(); sessao.current = ac; setErro(''); setFase('preparando');
    try {
      // Mesmo requisito da rota de voz; nenhuma chave chega ao navegador.
      const provedores = await api.get<{ tipo: string; chave_final: string | null }[]>('/v1/provedores', { signal: ac.signal });
      if (!ativo(ac)) return;
      if (!provedores.some(p => ['openai', 'compativel_openai'].includes(p.tipo) && p.chave_final)) throw new AvisoVoz(MSG_SEM_VOZ);
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new AvisoVoz('Seu navegador não oferece suporte ao microfone.');
      await ouvir(ac);
    } catch (falha) { falhou(falha, ac); }
  };
  const interromper = () => {
    const ac = sessao.current; if (!ac) return;
    if (fase === 'falando') { limparAudio.current(); void ouvir(ac); }
    else {
      if (fase === 'aguardando') { const id = lerEstado().agentes[agenteId]?.conversaId; if (id) void pararConversa(id).catch(() => {}); }
      encerrar();
    }
  };
  const acoes = useRef({ encerrar, interromper, ouvir, falhou });
  useEffect(() => { acoes.current = { encerrar, interromper, ouvir, falhou }; });
  useEffect(() => {
    const tecla = (ev: KeyboardEvent) => { if (ev.key === 'Escape' && sessao.current) { ev.preventDefault(); ev.stopImmediatePropagation(); acoes.current.interromper(); } };
    window.addEventListener('keydown', tecla, true);
    return () => { window.removeEventListener('keydown', tecla, true); acoes.current.encerrar(); };
  }, [agenteId]);
  useEffect(() => {
    const ac = sessao.current;
    if (!ac || fase !== 'aguardando' || gerandoNa(estado, agenteId, 0)) return;
    const novas = mensagensDa(estado, agenteId, 0).filter(m => !anteriores.current.has(m.id) && m.autor !== 'usuario' && !m.gerando);
    if (!novas.length) return;
    const timer = setTimeout(() => {
      clearTimeout(prazo.current);
      if (novas.some(m => m.estado === 'interrompida')) { acoes.current.encerrar(); return; }
      setFase('falando');
      let audio: HTMLAudioElement | undefined, url: string | undefined;
      const fala = new AbortController();
      limparAudio.current = () => { fala.abort(); if (audio) { audio.onended = null; audio.pause(); } if (url) URL.revokeObjectURL(url); };
      void sintetizarFala(novas.map(m => m.texto).join('\n'), fala.signal).then(async blob => {
        if (ac.signal.aborted || fala.signal.aborted) return;
        url = URL.createObjectURL(blob); audio = new Audio(url);
        audio.onended = () => { if (!ac.signal.aborted) void acoes.current.ouvir(ac); };
        audio.onerror = () => acoes.current.falhou(new AvisoVoz('Não foi possível tocar a resposta.'), ac);
        await audio.play();
      }).catch(falha => { if (!fala.signal.aborted) acoes.current.falhou(falha, ac); });
    }, 500);
    return () => clearTimeout(timer);
  }, [estado, fase, agenteId]);

  const ativa = fase !== 'inativo';
  // Faixa de estado (só durante a conversa ou com erro): vai para o contêiner acima do compositor, quando existe.
  const faixaDeEstado = (ativa || erro) ? <div className="conversa-voz">
    {ativa && <>
      <SoraOrb size={28} color={cor} movimento={movimento} state={fase === 'ouvindo' ? 'listening' : 'thinking'} title={rotulos[fase]} />
      <span role="status">{rotulos[fase]}</span>
      {fase === 'falando' && <button type="button" className="conversa-voz-acao" onClick={interromper}>Interromper leitura</button>}
    </>}
    {erro && <span role="alert">{erro}</span>}
  </div> : null;
  return <>
    {/* O gatilho é um ícone dentro do campo (ao lado do microfone e do Enviar). */}
    {ativa
      ? <button type="button" className="icon-button is-live" aria-label="Encerrar conversa por voz" title="Encerrar conversa por voz" onClick={encerrar}><IconeVoz /></button>
      : <button type="button" className="icon-button" aria-label="Conversar por voz" title="Conversar por voz" disabled={gerandoNa(estado, agenteId, 0)} onClick={() => void iniciar()}><IconeVoz /></button>}
    {faixa ? createPortal(faixaDeEstado, faixa) : faixaDeEstado}
  </>;
}

function IconeVoz() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" /></svg>;
}

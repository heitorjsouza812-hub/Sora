// Grava o microfone do compositor (o mesmo stream do VoiceBeam) e transcreve ao parar.
// Sem MediaRecorder (ou sem provedor de voz) o microfone segue só como efeito visual, com aviso em PT-BR.
import { useCallback, useEffect, useRef, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { transcreverAudio } from '../../api/voz';

const TIPOS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
const MIN_BYTES = 1500; // clique sem fala

export function useGravacaoVoz(stream: MediaStream | null | undefined, aoTexto: (texto: string) => void) {
  const [transcrevendo, setTranscrevendo] = useState(false);
  const [erro, setErro] = useState('');
  const destino = useRef(aoTexto);
  useEffect(() => { destino.current = aoTexto; });
  const descartar = useRef(false);
  /** Chamado ao enviar a mensagem com o microfone aberto: a fala em curso não vai para o campo. */
  const descartarGravacao = useCallback(() => { descartar.current = true; }, []);

  useEffect(() => {
    if (!stream || typeof MediaRecorder === 'undefined') return;
    const tipo = TIPOS.find(t => MediaRecorder.isTypeSupported?.(t));
    let rec: MediaRecorder;
    try { rec = new MediaRecorder(stream, tipo ? { mimeType: tipo } : undefined); } catch { return; }
    const pedacos: Blob[] = [];
    descartar.current = false;
    rec.onstart = () => setErro('');
    rec.ondataavailable = e => { if (e.data.size) pedacos.push(e.data); };
    rec.onstop = () => {
      if (descartar.current) { descartar.current = false; return; }
      const audio = new Blob(pedacos, { type: rec.mimeType || tipo || 'audio/webm' });
      if (audio.size < MIN_BYTES) return;
      setTranscrevendo(true);
      transcreverAudio(audio)
        .then(texto => { if (texto) destino.current(texto); else setErro('Não ouvi nada. Tente falar de novo.'); })
        .catch(e => setErro(mensagemDeErro(e)))
        .finally(() => setTranscrevendo(false));
    };
    rec.start();
    return () => { if (rec.state !== 'inactive') rec.stop(); };
  }, [stream]);

  return { transcrevendo, erro, descartarGravacao };
}

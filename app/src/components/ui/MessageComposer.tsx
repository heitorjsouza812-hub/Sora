import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { BorderBeam } from 'border-beam';
import { VoiceBeam, useMicrophone, type VoiceBeamMotion } from 'voice-glow';
import { useProjetos } from '../../state/projetos';
import { ToolsPopover } from '../review/ToolsPopover';
import { MicIcon, PlusIcon, SendIcon } from './Icons';

interface Props {
  placeholder: string;
  onSend?: (text: string) => void;
  /** valor inicial (modo não controlado) */
  initialValue?: string;
  /** modo controlado: o pai guarda o texto */
  value?: string;
  onValueChange?: (text: string) => void;
  processing?: boolean;
  compact?: boolean;
  tools?: boolean;
  accent?: string;
  /** digitando, com foco ou microfone ao vivo → true (a Sora fica "ouvindo") */
  onActivity?: (active: boolean) => void;
  /** microfone ao vivo ligado/desligado */
  onMicChange?: (live: boolean) => void;
}

const processingMotion = (): VoiceBeamMotion => ({
  gather: .8,
  offset: Math.sin(Date.now() / 650) * .72,
  stretch: .35,
  heldLevel: .45,
  cornerFollow: .5,
});

const avisoMic: Record<string, string> = {
  requesting: 'Permita o acesso ao microfone no navegador…',
  denied: 'Permita o acesso ao microfone nas configurações do navegador para falar com a Sora.',
  unsupported: 'Seu navegador não oferece suporte ao microfone.',
  error: 'Não foi possível iniciar o microfone. Tente novamente.',
};

export function MessageComposer({
  placeholder, onSend, initialValue = '', value: controlado, onValueChange, processing = false,
  compact = false, tools = false, accent, onActivity, onMicChange,
}: Props) {
  const [interno, setInterno] = useState(initialValue);
  const value = controlado ?? interno;
  const setValue = (v: string) => { if (controlado === undefined) setInterno(v); onValueChange?.(v); };
  const [focused, setFocused] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsRef = useRef<HTMLButtonElement>(null);
  const mic = useMicrophone();
  const live = mic.state === 'live';
  const active = focused || value.trim().length > 0 || live;
  const avisoId = useId();
  const aviso = avisoMic[mic.state];
  const { pluginsConectados } = useProjetos();

  useEffect(() => {
    const query = window.matchMedia('(max-width: 767px)');
    const update = () => setMobile(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  // microfone ao vivo também conta como atividade (a Sora passa a "ouvir")
  const cb = useRef({ onActivity, onMicChange, typing: false });
  useEffect(() => { cb.current.onActivity = onActivity; cb.current.onMicChange = onMicChange; });
  useEffect(() => {
    cb.current.onMicChange?.(live);
    cb.current.onActivity?.(live || cb.current.typing);
  }, [live]);

  const atividade = (typing: boolean) => { cb.current.typing = typing; onActivity?.(typing || live); };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = value.trim();
    if (!text || !onSend) return;
    onSend(text);
    setValue('');
    cb.current.typing = false;
    if (live) mic.stop();
  };

  return (
    <BorderBeam size="md" colorVariant="colorful" strength={0.7} theme="dark" active={active} className="composer-beam">
      <VoiceBeam
        type={mobile ? 'mobile' : undefined}
        stream={mic.stream}
        motion={processing ? processingMotion : undefined}
        active={live || processing}
        theme="dark"
        strength={0.72}
        className="voice-beam-wrap"
        data-processing={processing ? 'true' : 'false'}
      >
        <form className={`composer ${compact ? 'composer-compact' : ''}`} onSubmit={submit} style={accent ? { borderColor: `${accent}45` } : undefined}>
          <textarea
            value={value}
            rows={compact ? 1 : 2}
            aria-label={placeholder}
            placeholder={live ? 'Ouvindo…' : placeholder}
            aria-describedby={aviso ? avisoId : undefined}
            onChange={(event) => { setValue(event.target.value); atividade(event.target.value.length > 0); }}
            onFocus={() => { setFocused(true); atividade(true); }}
            onBlur={() => { setFocused(false); atividade(value.length > 0); }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-actions">
            {tools && <>
              <button type="button" className="add-button" aria-label="Anexar arquivo (em breve)" title="Anexar arquivo (em breve)" disabled><PlusIcon /></button>
              <button type="button" ref={toolsRef} className="tool-button" aria-haspopup="dialog" aria-expanded={toolsOpen} onClick={() => setToolsOpen((v) => !v)}>Ferramentas</button>
              <ToolsPopover open={toolsOpen} onClose={() => setToolsOpen(false)} anchorRef={toolsRef} plugins={pluginsConectados} />
            </>}
            <span className="composer-spacer" />
            <button
              type="button"
              className={`icon-button ${live ? 'is-live' : ''}`}
              aria-label={live ? 'Parar microfone' : 'Ativar microfone'}
              aria-pressed={live}
              disabled={mic.state === 'unsupported'}
              onClick={() => live ? mic.stop() : void mic.start()}
            ><MicIcon /></button>
            <button type="submit" className="send-button" aria-label="Enviar mensagem" disabled={!value.trim() || !onSend}><SendIcon /></button>
          </div>
          <span id={avisoId} className={`composer-notice ${aviso ? 'is-on' : ''}`} role="status" aria-live="polite">{aviso ?? ''}</span>
        </form>
      </VoiceBeam>
    </BorderBeam>
  );
}

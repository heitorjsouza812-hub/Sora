import { useEffect, useState, type FormEvent } from 'react';
import { BorderBeam } from 'border-beam';
import { VoiceBeam, useMicrophone, type VoiceBeamMotion } from 'voice-glow';
import { MicIcon, PlusIcon, SendIcon } from './Icons';

interface Props {
  placeholder: string;
  onSend?: (text: string) => void;
  initialValue?: string;
  processing?: boolean;
  compact?: boolean;
  tools?: boolean;
  accent?: string;
  onActivity?: (active: boolean) => void;
}

const processingMotion = (): VoiceBeamMotion => ({
  gather: .8,
  offset: Math.sin(Date.now() / 650) * .72,
  stretch: .35,
  heldLevel: .45,
  cornerFollow: .5,
});

export function MessageComposer({ placeholder, onSend, initialValue = '', processing = false, compact = false, tools = false, accent, onActivity }: Props) {
  const [value, setValue] = useState(initialValue);
  const [focused, setFocused] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  const mic = useMicrophone();
  const active = focused || value.trim().length > 0 || mic.state === 'live';

  useEffect(() => {
    const query = window.matchMedia('(max-width: 767px)');
    const update = () => setMobile(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = value.trim();
    if (!text || !onSend) return;
    onSend(text);
    setValue('');
  };

  return (
    <BorderBeam size="md" colorVariant="colorful" strength={0.7} theme="dark" active={active} className="composer-beam">
      <VoiceBeam
        type={mobile ? 'mobile' : undefined}
        stream={mic.stream}
        motion={processing ? processingMotion : undefined}
        active={mic.state === 'live' || processing}
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
            placeholder={placeholder}
            onChange={(event) => {
              setValue(event.target.value);
              onActivity?.(event.target.value.length > 0);
            }}
            onFocus={() => { setFocused(true); onActivity?.(true); }}
            onBlur={() => { setFocused(false); onActivity?.(value.length > 0); }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-actions">
            {tools && <><button type="button" className="add-button" aria-label="Adicionar"><PlusIcon /></button><button type="button" className="tool-button">Ferramentas</button></>}
            <span className="composer-spacer" />
            <button
              type="button"
              className={`icon-button ${mic.state === 'live' ? 'is-live' : ''}`}
              aria-label={mic.state === 'live' ? 'Parar microfone' : 'Ativar microfone'}
              aria-pressed={mic.state === 'live'}
              onClick={() => mic.state === 'live' ? mic.stop() : void mic.start()}
            ><MicIcon /></button>
            <button type="submit" className="send-button" aria-label="Enviar mensagem" disabled={!value.trim() || !onSend}><SendIcon /></button>
          </div>
        </form>
      </VoiceBeam>
    </BorderBeam>
  );
}


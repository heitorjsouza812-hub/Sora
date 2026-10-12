import { useEffect, useId, useRef, useState, type ClipboardEvent, type FormEvent, type ReactNode } from 'react';
import { BorderBeam } from 'border-beam';
import { VoiceBeam, useMicrophone, type VoiceBeamMotion } from 'voice-glow';
import { useProjetos } from '../../state/projetos';
import { ToolsPopover } from '../review/ToolsPopover';
import { EVENTO_ANEXAR, ListaAnexos, MAX_ANEXOS, useAnexos, type Anexo } from '../anexos';
import '../anexos/anexos.css';
import { AvisoCreditos, useConexao, useCreditosEsgotados } from '../erros';
import { Button } from '../base';
import { MicIcon, PlusIcon, SendIcon } from './Icons';

interface Props {
  placeholder: string;
  /** texto e anexos (com anexos e sem texto, o texto chega '') */
  onSend?: (text: string, anexos: Anexo[]) => void;
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
  /** botão "+", colar e soltar arquivos (padrão: ligado) */
  anexar?: boolean;
  /** resposta sendo gerada: Enviar vira Parar e Enter não envia */
  gerando?: boolean;
  onParar?: () => void;
  /** controles extras na barra do campo, depois de "Ferramentas" (ex.: Equipe / Agente independente) */
  extras?: ReactNode;
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
  compact = false, tools = false, accent, onActivity, onMicChange, anexar = true, gerando = false, onParar, extras,
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
  const { anexos, erro: erroAnexo, adicionar, remover, entregar } = useAnexos();
  const arquivoRef = useRef<HTMLInputElement>(null);
  const { online, tentarDeNovo } = useConexao();
  const semCreditos = useCreditosEsgotados();
  const bloqueado = !online || semCreditos;
  const podeEnviar = Boolean(onSend) && !bloqueado && (value.trim().length > 0 || anexos.length > 0);
  const podeParar = gerando && Boolean(onParar);

  // arquivos soltos na área do chat (<ZonaSoltar>) chegam por evento
  useEffect(() => {
    if (!anexar) return;
    const aoAnexar = (e: Event) => adicionar((e as CustomEvent<File[]>).detail ?? []);
    window.addEventListener(EVENTO_ANEXAR, aoAnexar);
    return () => window.removeEventListener(EVENTO_ANEXAR, aoAnexar);
  }, [anexar, adicionar]);

  // Esc para a resposta mesmo fora do campo, se não houver modal/menu aberto
  const pararRef = useRef(onParar);
  useEffect(() => { pararRef.current = onParar; });
  useEffect(() => {
    if (!podeParar) return;
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      if (document.querySelector('[aria-modal="true"], .sora-popover')) return;
      e.preventDefault();
      pararRef.current?.();
    };
    document.addEventListener('keydown', aoTeclar);
    return () => document.removeEventListener('keydown', aoTeclar);
  }, [podeParar]);

  const colar = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    if (!anexar) return;
    const arquivos = Array.from(event.clipboardData.files);
    if (!arquivos.length) return;
    event.preventDefault();
    adicionar(arquivos);
  };

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
    if (gerando) { onParar?.(); return; }
    const text = value.trim();
    if (!onSend || bloqueado || (!text && !anexos.length)) return;
    onSend(text, entregar());
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
          <ListaAnexos anexos={anexos} onRemover={remover} />
          <textarea
            value={value}
            rows={compact ? 1 : 2}
            aria-label={placeholder}
            placeholder={live ? 'Ouvindo…' : placeholder}
            aria-describedby={aviso ? avisoId : undefined}
            onChange={(event) => { setValue(event.target.value); atividade(event.target.value.length > 0); }}
            onFocus={() => { setFocused(true); atividade(true); }}
            onBlur={() => { setFocused(false); atividade(value.length > 0); }}
            onPaste={colar}
            onKeyDown={(event) => {
              if (event.key === 'Escape' && podeParar) {
                event.preventDefault();
                onParar?.();
                return;
              }
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (!gerando) event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-actions">
            {anexar && <>
              <button type="button" className="add-button" aria-label="Anexar arquivos" title={`Anexar arquivos (até ${MAX_ANEXOS}, 20 MB cada)`}
                disabled={anexos.length >= MAX_ANEXOS} onClick={() => arquivoRef.current?.click()}><PlusIcon /></button>
              <input ref={arquivoRef} type="file" multiple className="composer-file" tabIndex={-1} aria-hidden="true"
                onChange={(event) => { adicionar(Array.from(event.target.files ?? [])); event.target.value = ''; }} />
            </>}
            {tools && <>
              <button type="button" ref={toolsRef} className="tool-button" aria-haspopup="dialog" aria-expanded={toolsOpen} onClick={() => setToolsOpen((v) => !v)}>Ferramentas</button>
              <ToolsPopover open={toolsOpen} onClose={() => setToolsOpen(false)} anchorRef={toolsRef} plugins={pluginsConectados} />
            </>}
            {extras}
            <span className="composer-spacer" />
            <button
              type="button"
              className={`icon-button ${live ? 'is-live' : ''}`}
              aria-label={live ? 'Parar microfone' : 'Ativar microfone'}
              aria-pressed={live}
              disabled={mic.state === 'unsupported'}
              onClick={() => live ? mic.stop() : void mic.start()}
            ><MicIcon /></button>
            {podeParar
              ? <button type="button" className="send-button is-parar" aria-label="Parar resposta" title="Parar (Esc)" onClick={() => onParar?.()}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
                </button>
              : <button type="submit" className="send-button" aria-label="Enviar mensagem" disabled={!podeEnviar}><SendIcon /></button>}
          </div>
          <span id={avisoId} className={`composer-notice ${aviso ? 'is-on' : ''}`} role="status" aria-live="polite">{aviso ?? ''}</span>
          {erroAnexo && <p className="composer-erro" role="alert">{erroAnexo}</p>}
          {!online
            ? <div className="composer-bloqueio" role="status"><span>Sem conexão: dá para escrever, e você envia quando a internet voltar.</span><Button tamanho="P" onClick={tentarDeNovo}>Tentar de novo</Button></div>
            : semCreditos && <AvisoCreditos compacto />}
        </form>
      </VoiceBeam>
    </BorderBeam>
  );
}

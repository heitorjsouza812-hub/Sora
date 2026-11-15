import { createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ClipboardEvent, type FormEvent, type ReactNode } from 'react';
import { BorderBeam } from 'border-beam';
import { useGravacaoVoz } from './useGravacaoVoz';
import { VoiceBeam, useMicrophone, type VoiceBeamMotion } from 'voice-glow';
import { useProjetos } from '../../state/projetos';
import { ToolsPopover } from './ToolsPopover';
import { EVENTO_ANEXAR, ListaAnexos, MAX_ANEXOS, useAnexos, type Anexo } from '../anexos';
import '../anexos/anexos.css';
import { useConexao } from '../erros';
import { Button } from '../base';
import { MicIcon, PlusIcon, SendIcon } from './Icons';
import { useMedia } from './useMedia';
import './compositor.css';

interface Props {
  /** texto do campo; também é o rótulo acessível (aria-label) */
  placeholder: string;
  /** versão curta para o celular, quando o nome não cabe (padrão: "Mensagem…" se o texto passar de 26 letras) */
  placeholderCurto?: string;
  /** texto e anexos (com anexos e sem texto, o texto chega '') */
  onSend?: (text: string, anexos: Anexo[]) => void;
  /** valor inicial (modo não controlado) */
  initialValue?: string;
  /** modo controlado: o pai guarda o texto */
  value?: string;
  onValueChange?: (text: string) => void;
  processing?: boolean;
  /** @deprecated o compositor é um só; use `grande` para o estado vazio da Sora */
  compact?: boolean;
  /** estado vazio da Sora (desktop): texto em cima, ações embaixo, altura mínima de 120 px */
  grande?: boolean;
  tools?: boolean;
  /** digitando, com foco ou microfone ao vivo → true (a Sora fica "ouvindo") */
  onActivity?: (active: boolean) => void;
  /** microfone ao vivo ligado/desligado */
  onMicChange?: (live: boolean) => void;
  /** botão "+", colar e soltar arquivos (padrão: ligado) */
  anexar?: boolean;
  /** resposta sendo gerada: Enviar vira Parar e Enter não envia */
  gerando?: boolean;
  onParar?: () => void;
  /** controles extras à esquerda, depois de "Ferramentas" */
  extras?: ReactNode;
  /** botões extras à direita, antes do microfone e do Enviar (ex.: @ no grupo, conversar por voz no bot) */
  acoesDireita?: ReactNode;
  /** voz fica restrita ao chat 1:1 do bot na interface da etapa 5 */
  voz?: boolean;
  /** muda de valor → o foco vai para o campo (com o cursor no fim) */
  focoSinal?: number;
}

// O BorderBeam e o VoiceBeam têm um efeito que depende de `children` e grava um objeto novo a cada execução: com `children`
// novo a cada tecla, cada letra dispara uma atualização extra e, digitando rápido, o React estoura o limite de
// atualizações aninhadas e engole teclas. Então os dois recebem SEMPRE o mesmo elemento (CorpoDoCampo / CorpoDoFormulario), e o
// conteúdo de verdade chega por contexto.
const ConteudoDoCampo = createContext<ReactNode>(null);
function CorpoDoCampo() { return <>{useContext(ConteudoDoCampo)}</>; }
const FormularioDoCampo = createContext<ReactNode>(null);
function CorpoDoFormulario() { return <>{useContext(FormularioDoCampo)}</>; }
const CORPO_DO_FORMULARIO = <CorpoDoFormulario />;
const CORPO_ESTAVEL = <CorpoDoCampo />;
const BEAM_CSS = `
[data-beam="{id}"][data-active], [data-beam="{id}"][data-fading] {
  animation-duration: 3.2s, 320ms;
}
[data-beam="{id}"] { transition: --beam-strength 320ms var(--ease); }
`;

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
  placeholder, placeholderCurto, onSend, initialValue = '', value: controlado, onValueChange, processing = false,
  grande = false, tools = false, onActivity, onMicChange, anexar = true, gerando = false, onParar, extras, acoesDireita, voz = false, focoSinal,
}: Props) {
  const campoRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!focoSinal) return;
    const quadro = requestAnimationFrame(() => { const c = campoRef.current; if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } });
    return () => cancelAnimationFrame(quadro);
  }, [focoSinal]);
  const [interno, setInterno] = useState(initialValue);
  const value = controlado ?? interno;
  const setValue = (v: string) => { if (controlado === undefined) setInterno(v); onValueChange?.(v); };
  const [focused, setFocused] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsRef = useRef<HTMLButtonElement>(null);
  const mic = useMicrophone();
  const live = mic.state === 'live';
  const movimentoReduzido = useMedia('(prefers-reduced-motion: reduce)');
  // beam: aparece no foco (0,45) e fica mais forte enquanto digita ou fala (0,7); sem movimento, só a borda de foco (CSS)
  const [digitando, setDigitando] = useState(false);
  const fimDigitacao = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(fimDigitacao.current), []);
  const marcarDigitacao = () => { setDigitando(true); window.clearTimeout(fimDigitacao.current); fimDigitacao.current = window.setTimeout(() => setDigitando(false), 1200); };
  const active = !movimentoReduzido && (focused || live);
  const forcaBeam = live || digitando ? 0.7 : 0.45;
  const avisoId = useId();
  const valorRef = useRef(value);
  useEffect(() => { valorRef.current = value; });
  const { transcrevendo, erro: erroVoz, descartarGravacao } = useGravacaoVoz(mic.stream, texto => {
    const atual = valorRef.current;
    setValue(atual && !/s$/.test(atual) ? `${atual} ${texto}` : `${atual}${texto}`);
  });
  const aviso = avisoMic[mic.state] ?? (transcrevendo ? 'Transcrevendo sua fala…' : erroVoz || undefined);
  const { pluginsConectados } = useProjetos();
  const { anexos, erro: erroAnexo, adicionar, remover, entregar } = useAnexos();
  const arquivoRef = useRef<HTMLInputElement>(null);
  const { online, tentarDeNovo } = useConexao();
  const bloqueado = !online;
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

  // o campo cresce com o texto até 200 px; depois rola por dentro
  useLayoutEffect(() => {
    const c = campoRef.current; if (!c) return;
    c.style.height = 'auto';
    if (c.scrollHeight > 0) c.style.height = `${Math.min(c.scrollHeight, 200)}px`;
  }, [value, mobile]);

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
    if (live) { descartarGravacao(); mic.stop(); }
  };

  const formulario = (
        <form className={`composer ${grande ? 'composer-grande' : 'composer-compact'}`} onSubmit={submit}>
          <ListaAnexos anexos={anexos} onRemover={remover} />
          <textarea
            ref={campoRef}
            value={value}
            rows={1}
            aria-label={placeholder}
            placeholder={live ? 'Ouvindo…' : mobile ? (placeholderCurto ?? (placeholder.length > 26 ? 'Mensagem…' : placeholder)) : placeholder}
            aria-describedby={aviso ? avisoId : undefined}
            onChange={(event) => { setValue(event.target.value); atividade(event.target.value.length > 0); marcarDigitacao(); }}
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
          <div className="composer-esq">
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
          </div>
          <div className="composer-dir">
            {acoesDireita}
            {voz && <button
              type="button"
              className={`icon-button ${live ? 'is-live' : ''}`}
              aria-label={live ? 'Parar microfone' : 'Ativar microfone'}
              aria-pressed={live}
              disabled={mic.state === 'unsupported'}
              onClick={() => live ? mic.stop() : void mic.start()}
            ><MicIcon /></button>}
            {podeParar
              ? <button type="button" className="send-button is-parar" aria-label="Parar resposta" title="Parar (Esc)" onClick={() => onParar?.()}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
                </button>
              : <button type="submit" className="send-button" aria-label="Enviar mensagem" disabled={!podeEnviar}><SendIcon /></button>}
          </div>
          <span id={avisoId} className={`composer-notice ${aviso ? 'is-on' : ''}`} role="status" aria-live="polite">{aviso ?? ''}</span>
          {erroAnexo && <p className="composer-erro" role="alert">{erroAnexo}</p>}
          {!online && <div className="composer-bloqueio" role="status"><span>Sem conexão: dá para escrever, e você envia quando a internet voltar.</span><Button tamanho="P" onClick={tentarDeNovo}>Tentar de novo</Button></div>}
        </form>
  );
  const conteudo = (
      <VoiceBeam
        type={mobile ? 'mobile' : undefined}
        stream={voz ? mic.stream : null}
        motion={processing ? processingMotion : undefined}
        active={(voz && live) || processing}
        theme="dark"
        strength={0.72}
        className="voice-beam-wrap"
        data-processing={processing ? 'true' : 'false'}
      >
        {CORPO_DO_FORMULARIO}
      </VoiceBeam>
  );

  return (
    <FormularioDoCampo.Provider value={formulario}>
    <ConteudoDoCampo.Provider value={conteudo}>
      <BorderBeam size="md" colorVariant="colorful" strength={forcaBeam} duration={3.2} css={BEAM_CSS} theme="dark" active={active} className="composer-beam">{CORPO_ESTAVEL}</BorderBeam>
    </ConteudoDoCampo.Provider>
    </FormularioDoCampo.Provider>
  );
}

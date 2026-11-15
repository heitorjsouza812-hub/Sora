import { AnexosResposta } from './AnexosResposta';
import { FontesMensagem } from './FontesMensagem';
// Uma mensagem do chat (usuário, Sora ou agente) com streaming, markdown e ações:
// copiar · refazer · 👍/👎 · editar a pergunta. As ações aparecem no hover/foco; no celular, pelo
// botão "…" ou por toque longo.
import { Fragment, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import {
  avaliarMensagem, tentarEnvioNovamente, editarPergunta, podeEditar, podeRefazer, previaDoAnexo, refazerResposta, textoVisivel, useProjetos, type MensagemChat as Msg,
} from '../../state/projetos';
import { ouvirTexto, pararFala } from '../../api/voz';
import { mensagemDeErro } from '../../api/cliente';
import { ListaAnexos } from '../anexos';
import { IconButton, Tooltip, toast } from '../base';
import { Markdown } from './Markdown';
import './mensagens.css';

const Ic = {
  copiar: <svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>,
  refazer: <svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></svg>,
  positiva: <svg viewBox="0 0 24 24"><path d="M7 11v9H4v-9zM7 11l4-7c1.5 0 2.5 1.2 2.2 2.7L12.6 10H18a2 2 0 0 1 2 2.3l-1.2 6A2 2 0 0 1 16.8 20H7" /></svg>,
  negativa: <svg viewBox="0 0 24 24"><path d="M17 13V4h3v9zM17 13l-4 7c-1.5 0-2.5-1.2-2.2-2.7l.6-3.3H6a2 2 0 0 1-2-2.3l1.2-6A2 2 0 0 1 7.2 4H17" /></svg>,
  editar: <svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></svg>,
  ouvir: <svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7" /></svg>,
  copiado: <svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>,
  mais: <svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg>,
};

/** @todos e @nome na bolha do usuário: azul de link, peso 500 (o resto do texto fica como está). */
function comMencoes(texto: string): ReactNode {
  const partes = texto.split(/(@[\p{L}\p{N}_-]+)/gu);
  if (partes.length === 1) return texto;
  return partes.map((p, i) => i % 2 ? <span key={i} className="mencao">{p}</span> : <Fragment key={i}>{p}</Fragment>);
}

const copiar = (texto: string) => {
  void navigator.clipboard?.writeText(texto).then(() => toast({ mensagem: 'Copiado', tom: 'sucesso' }), () => toast({ mensagem: 'Não foi possível copiar', tom: 'erro' }));
};

function Acao({ rotulo, icone, onClick, ativo, ok }: { rotulo: string; icone: ReactNode; onClick: () => void; ativo?: boolean; ok?: boolean }) {
  return (
    <Tooltip conteudo={rotulo}>
      <IconButton aria-label={rotulo} icone={icone} tamanho="P" onClick={onClick} aria-pressed={ativo === undefined ? undefined : ativo}
        className={`msg-acao${ativo ? ' is-on' : ''}${ok ? ' is-ok' : ''}`} />
    </Tooltip>
  );
}

export interface MensagemChatProps {
  m: Msg;
  agora: number;
  /** avatar (orb) da Sora ou do agente; ausente nas mensagens do usuário */
  avatar?: ReactNode;
  /** nome em destaque antes do texto (ex.: nome do agente, na cor dele) */
  nome?: string;
  cor?: string;
  /** texto cinza depois do nome (no grupo: "entregou") */
  rotulo?: string;
  /** última resposta da conversa: as ações ficam sempre visíveis */
  ultima?: boolean;
  /** quem responde a esta pergunta (nome, avatar, cor): usado quando a pergunta foi interrompida antes de a resposta começar, para o aviso ocupar o lugar da resposta */
  respostaDe?: { nome?: string; avatar?: ReactNode; cor?: string };
}

export function MensagemChat({ m, agora, avatar, nome, cor, rotulo, ultima = false, respostaDe }: MensagemChatProps) {
  const e = useProjetos();
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState(m.texto);
  const [abertas, setAbertas] = useState(false);
  // só a mensagem recém-criada anima na entrada; histórico e recarga da página não
  const [nova] = useState(() => Date.now() - m.criadoEm < 4000);
  const toque = useRef(0);
  const [salvando, setSalvando] = useState(false);
  const executar = async (acao: () => Promise<void>) => {
    if (salvando) return; setSalvando(true);
    try { await acao(); setEditando(false); } catch (erro) { toast({ mensagem: mensagemDeErro(erro), tom: 'erro' }); } finally { setSalvando(false); }
  };
  const usuario = m.autor === 'usuario';
  const vis = textoVisivel(m, agora);
  const editavel = podeEditar(e, m);
  const [ouvindo, setOuvindo] = useState(false);
  const [copiou, setCopiou] = useState(false);
  const aoCopiar = () => { copiar(m.texto); setCopiou(true); window.setTimeout(() => setCopiou(false), 1200); };
  const ouvir = () => {
    if (ouvindo) { pararFala(); return; }
    setOuvindo(true);
    void ouvirTexto(m.texto).catch(erro => toast({ mensagem: mensagemDeErro(erro), tom: 'erro' })).finally(() => setOuvindo(false));
  };

  // toque longo (celular) mostra as ações
  const toqueLongo = {
    onTouchStart: () => { window.clearTimeout(toque.current); toque.current = window.setTimeout(() => setAbertas(true), 500); },
    onTouchEnd: () => window.clearTimeout(toque.current),
    onTouchMove: () => window.clearTimeout(toque.current),
  };

  // parou antes do primeiro caractere: o aviso ocupa o lugar da resposta (a API grava "Resposta interrompida.")
  const soAviso = !usuario && vis.interrompida && (!vis.texto.trim() || /^resposta interrompida\.?$/i.test(vis.texto.trim()));
  const andarNasAcoes = (ev: KeyboardEvent<HTMLDivElement>) => {
    if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
    const botoes = Array.from(ev.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
    const i = botoes.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0) return;
    ev.preventDefault();
    botoes[(i + (ev.key === 'ArrowRight' ? 1 : botoes.length - 1)) % botoes.length].focus();
  };
  const acoes = !vis.gerando && !editando && !salvando && (
    <div className="msg-acoes" role="toolbar" aria-label="Ações da mensagem" onKeyDown={andarNasAcoes}>
      <Acao rotulo="Copiar" icone={copiou ? Ic.copiado : Ic.copiar} ok={copiou} onClick={aoCopiar} />
      {usuario && editavel && <Acao rotulo="Editar pergunta" icone={Ic.editar} onClick={() => { setRascunho(m.texto); setEditando(true); }} />}
      {!usuario && podeRefazer(m) && !vis.interrompida && <Acao rotulo="Refazer resposta" icone={Ic.refazer} onClick={() => void executar(() => refazerResposta(m.id))} />}
      {!usuario && e.mensagens.some(x => x.id === m.id) && <>
        <Acao rotulo="Boa resposta" icone={Ic.positiva} ativo={m.avaliacao === 'positiva'} onClick={() => void executar(() => avaliarMensagem(m.id, 'positiva'))} />
        <Acao rotulo="Resposta ruim" icone={Ic.negativa} ativo={m.avaliacao === 'negativa'} onClick={() => void executar(() => avaliarMensagem(m.id, 'negativa'))} />
      </>}
      {!usuario && m.texto.trim() && <Acao rotulo={ouvindo ? 'Parar áudio' : 'Ouvir'} icone={Ic.ouvir} ativo={ouvindo} onClick={ouvir} />}

    </div>
  );
  const mais = !vis.gerando && !editando && !salvando && (
    <IconButton className="msg-mais" aria-label="Mais ações" aria-expanded={abertas} tamanho="P" icone={Ic.mais} onClick={() => setAbertas(v => !v)} />
  );

  if (usuario) {
    return (<>
      <div id={`msg-${m.id}`} data-msg-id={m.id} className={`chat-msg is-user${nova ? ' is-nova' : ''} ${abertas ? 'is-acoes-abertas' : ''}${ultima ? ' is-ultima' : ''}`} {...toqueLongo}>
        {editando ? (
          <form className="msg-edit" onSubmit={ev => { ev.preventDefault(); if (rascunho.trim() || m.anexos?.length) { void executar(() => editarPergunta(m.id, rascunho)); } }}>
            <label className="sr-only" htmlFor={`edit-${m.id}`}>Editar pergunta</label>
            <textarea id={`edit-${m.id}`} value={rascunho} rows={3} autoFocus onChange={ev => setRascunho(ev.target.value)}
              onKeyDown={ev => { if (ev.key === 'Escape') setEditando(false); if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); ev.currentTarget.form?.requestSubmit(); } }} />
            <div className="msg-edit-acoes">
              <button type="button" className="msg-edit-cancelar" onClick={() => setEditando(false)}>Cancelar</button>
              <button type="submit" className="msg-edit-enviar" disabled={salvando || !rascunho.trim()}>Enviar</button>
            </div>
          </form>
        ) : <div className="user-linha">{acoes}{mais}{m.texto.trim() ? <div className="user-message">{comMencoes(m.texto)}</div> : null}</div>}
        {m.anexos?.length ? <ListaAnexos className="msg-anexos" anexos={m.anexos.map(x => ({ ...x, urlPrevia: previaDoAnexo(x.id) }))} /> : null}
        {m.envio === 'enviando' && <small role="status">Enviando…</small>}
        {m.envio === 'erro' && <div role="alert">Não foi possível enviar. <button type="button" onClick={() => void tentarEnvioNovamente(m.id)}>Tentar de novo</button></div>}
      </div>
      {/* parou antes do 1º caractere: o aviso é da resposta (com o cabeçalho do autor), nunca da pergunta */}
      {vis.interrompida && respostaDe && <div className="chat-msg is-assistant is-sem-resposta" style={respostaDe.cor ? { '--agent': respostaDe.cor } as CSSProperties : undefined}>
        {(respostaDe.avatar || respostaDe.nome) && <div className="msg-cabeca">{respostaDe.avatar}{respostaDe.nome && <strong className="msg-nome">{respostaDe.nome}</strong>}</div>}
        <div className="msg-corpo"><p className="msg-interrompida" role="status"><i aria-hidden="true" /><span>Resposta interrompida</span>{editavel && <button type="button" className="msg-refazer" disabled={salvando} onClick={() => void executar(() => editarPergunta(m.id, m.texto))}>Refazer resposta</button>}</p></div>
      </div>}
    </>);
  }

  return (
    <div id={`msg-${m.id}`} data-msg-id={m.id} className={`chat-msg is-assistant${nova ? ' is-nova' : ''} ${abertas ? 'is-acoes-abertas' : ''}${ultima ? ' is-ultima' : ''}`} style={cor ? { '--agent': cor } as CSSProperties : undefined} {...toqueLongo}>
      {(avatar || nome) && <div className="msg-cabeca">
        {avatar}
        {nome && <strong className="msg-nome">{nome}</strong>}
        {rotulo && <span className="msg-rotulo">{rotulo}</span>}
      </div>}
      <div className="msg-corpo">
        {!soAviso && <Markdown texto={vis.texto} gerando={vis.gerando} fontes={m.fontes} mensagemId={m.id} />}
        {!!m.fontes?.length && <FontesMensagem mensagemId={m.id} fontes={m.fontes} />}
        {!!m.anexos?.length && <AnexosResposta anexos={m.anexos} />}
        {vis.interrompida && <p className="msg-interrompida" role="status"><i aria-hidden="true" /><span>Resposta interrompida</span>{podeRefazer(m) && <button type="button" className="msg-refazer" disabled={salvando} onClick={() => void executar(() => refazerResposta(m.id))}>Refazer resposta</button>}</p>}
        <div className="msg-barra">{acoes}{mais}</div>
      </div>
    </div>
  );
}

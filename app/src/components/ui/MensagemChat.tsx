// Uma mensagem do chat (usuário, Sora ou agente) com streaming, markdown e ações:
// copiar · refazer · 👍/👎 · editar a pergunta. As ações aparecem no hover/foco; no celular, pelo
// botão "…" ou por toque longo.
import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import {
  avaliarMensagem, editarPergunta, podeEditar, podeRefazer, previaDoAnexo, refazerResposta, textoVisivel, useProjetos, type MensagemChat as Msg,
} from '../../state/projetos';
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
  mais: <svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg>,
};

const copiar = (texto: string) => {
  void navigator.clipboard?.writeText(texto).then(() => toast({ mensagem: 'Copiado', tom: 'sucesso' }), () => toast({ mensagem: 'Não foi possível copiar', tom: 'erro' }));
};

function Acao({ rotulo, icone, onClick, ativo }: { rotulo: string; icone: ReactNode; onClick: () => void; ativo?: boolean }) {
  return (
    <Tooltip conteudo={rotulo}>
      <IconButton aria-label={rotulo} icone={icone} tamanho="P" onClick={onClick} aria-pressed={ativo === undefined ? undefined : ativo}
        className={ativo ? 'msg-acao is-on' : 'msg-acao'} />
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
}

export function MensagemChat({ m, agora, avatar, nome, cor }: MensagemChatProps) {
  const e = useProjetos();
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState(m.texto);
  const [abertas, setAbertas] = useState(false);
  const toque = useRef(0);
  const usuario = m.autor === 'usuario';
  const vis = textoVisivel(m, agora);
  const editavel = podeEditar(e, m);

  // toque longo (celular) mostra as ações
  const toqueLongo = {
    onTouchStart: () => { window.clearTimeout(toque.current); toque.current = window.setTimeout(() => setAbertas(true), 500); },
    onTouchEnd: () => window.clearTimeout(toque.current),
    onTouchMove: () => window.clearTimeout(toque.current),
  };

  const acoes = !vis.gerando && !editando && (
    <div className="msg-acoes" role="toolbar" aria-label="Ações da mensagem">
      <Acao rotulo="Copiar" icone={Ic.copiar} onClick={() => copiar(m.texto)} />
      {usuario && editavel && <Acao rotulo="Editar pergunta" icone={Ic.editar} onClick={() => { setRascunho(m.texto); setEditando(true); }} />}
      {!usuario && podeRefazer(m) && <Acao rotulo="Refazer resposta" icone={Ic.refazer} onClick={() => refazerResposta(m.id)} />}
      {!usuario && <>
        <Acao rotulo="Boa resposta" icone={Ic.positiva} ativo={m.avaliacao === 'positiva'} onClick={() => avaliarMensagem(m.id, 'positiva')} />
        <Acao rotulo="Resposta ruim" icone={Ic.negativa} ativo={m.avaliacao === 'negativa'} onClick={() => avaliarMensagem(m.id, 'negativa')} />
      </>}
    </div>
  );
  const mais = !vis.gerando && !editando && (
    <IconButton className="msg-mais" aria-label="Mais ações" aria-expanded={abertas} tamanho="P" icone={Ic.mais} onClick={() => setAbertas(v => !v)} />
  );

  if (usuario) {
    return (
      <div className={`chat-msg is-user ${abertas ? 'is-acoes-abertas' : ''}`} {...toqueLongo}>
        {editando ? (
          <form className="msg-edit" onSubmit={ev => { ev.preventDefault(); if (rascunho.trim() || m.anexos?.length) { editarPergunta(m.id, rascunho); setEditando(false); } }}>
            <label className="sr-only" htmlFor={`edit-${m.id}`}>Editar pergunta</label>
            <textarea id={`edit-${m.id}`} value={rascunho} rows={3} autoFocus onChange={ev => setRascunho(ev.target.value)}
              onKeyDown={ev => { if (ev.key === 'Escape') setEditando(false); if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); ev.currentTarget.form?.requestSubmit(); } }} />
            <div className="msg-edit-acoes">
              <button type="button" className="msg-edit-cancelar" onClick={() => setEditando(false)}>Cancelar</button>
              <button type="submit" className="msg-edit-enviar" disabled={!rascunho.trim() && !m.anexos?.length}>Enviar</button>
            </div>
          </form>
        ) : m.texto.trim() ? <div className="user-message">{m.texto}</div> : null}
        {m.anexos?.length ? <ListaAnexos className="msg-anexos" anexos={m.anexos.map(x => ({ ...x, urlPrevia: previaDoAnexo(x.id) }))} /> : null}
        <div className="msg-barra">{acoes}{mais}</div>
      </div>
    );
  }

  return (
    <div className={`chat-msg is-assistant ${abertas ? 'is-acoes-abertas' : ''}`} style={cor ? { '--agent': cor } as CSSProperties : undefined} {...toqueLongo}>
      <div className="assistant-row">
        {avatar}
        <div className="msg-corpo">
          {nome && <strong className="msg-nome">{nome}</strong>}
          <Markdown texto={vis.texto} gerando={vis.gerando} />
          {vis.interrompida && <p className="msg-interrompida" role="status">Resposta interrompida</p>}
          <div className="msg-barra">{acoes}{mais}</div>
        </div>
      </div>
    </div>
  );
}

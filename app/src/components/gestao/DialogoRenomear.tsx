// Renomear projeto, agente ou a própria Sora.
import { useRef, useState } from 'react';
import { atualizarAgente, atualizarSora, renomearProjeto, useProjetos } from '../../state/projetos';
import { Modal } from '../overlay';
import type { AlvoGestao } from './acoes';
import './gestao.css';

export function DialogoRenomear({ alvo, onClose }: { alvo: AlvoGestao; onClose: () => void }) {
  const e = useProjetos();
  const campo = useRef<HTMLInputElement>(null);
  const sora = alvo.tipo === 'agente' && alvo.id === 'sora';
  const projeto = alvo.tipo === 'projeto' ? e.projetos.find((p) => p.id === alvo.id) : undefined;
  const agente = alvo.tipo === 'agente' && !sora ? e.agentes[alvo.id] : undefined;
  const nomeAtual = projeto?.titulo ?? agente?.nome ?? (sora ? e.sora.nome : '');
  const [nome, setNome] = useState(nomeAtual);
  if (!projeto && !agente && !sora) return null;

  const limpo = nome.trim();
  const valido = !!limpo && limpo !== nomeAtual;
  const salvar = () => {
    if (!valido) return;
    if (projeto) renomearProjeto(projeto.id, limpo);
    else if (agente) atualizarAgente(agente.id, { nome: limpo });
    else atualizarSora({ nome: limpo });
    onClose();
  };

  return (
    <Modal open onClose={onClose} size="sm" initialFocusRef={campo}
      title={projeto ? 'Renomear projeto' : `Renomear ${nomeAtual}`}
      footer={<div className="gestao-footer">
        <button type="button" className="gestao-btn-ghost" onClick={onClose}>Cancelar</button>
        <button type="button" className="gestao-btn" disabled={!valido} onClick={salvar}>Salvar</button>
      </div>}>
      <form className="gestao-field" onSubmit={(ev) => { ev.preventDefault(); salvar(); }}>
        <label htmlFor={`renomear-${alvo.id}`}>{projeto ? 'Título' : 'Nome'}</label>
        <input id={`renomear-${alvo.id}`} ref={campo} className="gestao-input" value={nome} maxLength={projeto ? 60 : 24}
          autoComplete="off" onChange={(ev) => setNome(ev.target.value)} onFocus={(ev) => ev.currentTarget.select()} />
      </form>
    </Modal>
  );
}

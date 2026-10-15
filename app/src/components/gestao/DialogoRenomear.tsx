// Renomear projeto, agente ou a própria Sora.
import { useRef, useState } from 'react';
import { atualizarAgente, atualizarSora, renomearProjeto, useProjetos } from '../../state/projetos';
import { Button, Input, toast } from '../base';
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
    toast({ mensagem: projeto ? (projeto.tipo === 'chat' ? 'Chat renomeado' : 'Projeto renomeado') : 'Agente renomeado', descricao: `Agora se chama “${limpo}”.`, tom: 'sucesso', duracao: 3500 });
    onClose();
  };

  return (
    <Modal open onClose={onClose} size="sm" initialFocusRef={campo}
      title={projeto ? 'Renomear projeto' : `Renomear ${nomeAtual}`}
      footer={<div className="gestao-footer">
        <Button variante="fantasma" onClick={onClose}>Cancelar</Button>
        <Button variante="primario" disabled={!valido} onClick={salvar}>Salvar</Button>
      </div>}>
      <form onSubmit={(ev) => { ev.preventDefault(); salvar(); }}>
        <Input ref={campo} rotulo={projeto ? 'Título' : 'Nome'} value={nome} maxLength={projeto ? 60 : 24} autoComplete="off"
          ajuda={`${nome.length}/${projeto ? 60 : 24}`} onChange={(ev) => setNome(ev.target.value)} onFocus={(ev) => ev.currentTarget.select()} />
      </form>
    </Modal>
  );
}

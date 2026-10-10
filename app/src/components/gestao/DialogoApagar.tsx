// Confirmação de "Apagar".
// • Projeto: diz quantos agentes saem junto e oferece "Manter os agentes como avulsos".
// • Agente: avisa em quais projetos ele participa (ele sai dessas equipes).
// • Sora: não pode ser apagada — o diálogo só explica.
import { useState, type CSSProperties } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { removerAgente, removerProjeto, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { Modal } from '../overlay';
import type { AlvoGestao } from './acoes';
import './gestao.css';

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

export function DialogoApagar({ alvo, onClose, onApagado }: { alvo: AlvoGestao; onClose: () => void; onApagado?: () => void }) {
  const e = useProjetos();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [manter, setManter] = useState(false);
  const sora = alvo.tipo === 'agente' && alvo.id === 'sora';
  const projeto = alvo.tipo === 'projeto' ? e.projetos.find((p) => p.id === alvo.id) : undefined;
  const agente = alvo.tipo === 'agente' && !sora ? e.agentes[alvo.id] : undefined;

  if (sora) {
    return (
      <Modal open onClose={onClose} size="sm" title={`${e.sora.nome} não pode ser apagada`}
        description="Ela é a agente principal: coordena as equipes e está sempre com você. Você pode renomear ou personalizar a Sora."
        footer={<div className="gestao-footer"><button type="button" className="gestao-btn" onClick={onClose}>Entendi</button></div>}>
        <div className="gestao-sora"><SoraOrb size={84} color={e.sora.cor} state="idle" decorative glow={false} /></div>
      </Modal>
    );
  }
  if (!projeto && !agente) return null;

  const equipe = projeto ? projeto.agenteIds.map((id) => e.agentes[id]).filter((a) => !!a) : [];
  const projetosDoAgente = agente ? e.projetos.filter((p) => p.agenteIds.includes(agente.id)) : [];

  const apagar = () => {
    let aberto = false;
    if (projeto) {
      aberto = pathname.includes(projeto.id) || (pathname === '/chat/sora' && e.projetoAtivoId === projeto.id)
        || (!manter && equipe.some((a) => pathname.includes(a.id)));
      removerProjeto(projeto.id, { manterAgentes: manter });
    } else if (agente) {
      aberto = pathname.includes(agente.id);
      removerAgente(agente.id);
    }
    onClose();
    onApagado?.();
    if (aberto) navigate('/');
  };

  const titulo = projeto
    ? (equipe.length && !manter ? `Apagar o projeto e ${equipe.length === 1 ? 'o agente' : `os ${equipe.length} agentes`}?` : 'Apagar o projeto?')
    : `Apagar ${agente!.nome}?`;
  const descricao = projeto
    ? `“${projeto.titulo}” — o chat, o plano, as entregas e o histórico de trabalho serão apagados. Não dá para desfazer.`
    : `${agente!.funcao}. A conversa e o histórico de trabalho serão apagados. Não dá para desfazer.`;

  return (
    <Modal open onClose={onClose} size="sm" title={titulo} description={descricao}
      footer={<div className="gestao-footer">
        <button type="button" className="gestao-btn-ghost" onClick={onClose}>Cancelar</button>
        <button type="button" className="gestao-btn gestao-danger" onClick={apagar}>Apagar</button>
      </div>}>
      {projeto && equipe.length > 0 && <>
        <p className="gestao-aviso">{manter
          ? `${plural(equipe.length, 'agente continua', 'agentes continuam')} em Agentes, como avulsos:`
          : `${plural(equipe.length, 'agente será apagado', 'agentes serão apagados')} junto:`}</p>
        <ul className="gestao-equipe">
          {equipe.map((a, i) => (
            <li key={a.id} style={{ '--cor': a.cor } as CSSProperties}>
              <SoraOrb size={26} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative seed={i + 3} />
              <span><strong>{a.nome}</strong><small>{a.funcao}</small></span>
            </li>
          ))}
        </ul>
        <label className="gestao-check">
          <input type="checkbox" checked={manter} onChange={(ev) => setManter(ev.target.checked)} />
          <span>Manter os agentes como avulsos</span>
        </label>
      </>}
      {agente && (projetosDoAgente.length > 0
        ? <>
          <p className="gestao-aviso">{agente.nome} participa de {plural(projetosDoAgente.length, 'projeto', 'projetos')} e sairá da equipe:</p>
          <ul className="gestao-projetos">{projetosDoAgente.map((p) => <li key={p.id}>{p.titulo}</li>)}</ul>
        </>
        : <p className="gestao-aviso">{agente.nome} não participa de nenhum projeto.</p>)}
    </Modal>
  );
}

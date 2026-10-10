// "Editar agente" aberto de qualquer lugar (barra lateral, equipe, cabeçalho do chat):
// as MESMAS peças do construtor (formulário Configurar + prévia). Modal no desktop, BottomSheet no celular.
// Salvar atualiza o store e reflete na hora em todo o app (avatar, status, barras, mensagens).
import { useState } from 'react';
import { COR_SORA } from '../../data/planejador';
import { definirModeloAgente, useModelos } from '../../state/modelos';
import { atualizarAgente, atualizarSora, useProjetos } from '../../state/projetos';
import { BottomSheet, Modal } from '../overlay';
import { useCelular } from '../ui/useMedia';
import { AgentConfigForm } from './AgentConfigForm';
import { AgentPreview } from './AgentPreview';
import type { RascunhoConstrutor } from './types';
import './builder.css';

export interface EditarAgenteModalProps {
  /** id do agente, ou 'sora' */
  agenteId: string;
  onFechar: () => void;
}

export function EditarAgenteModal({ agenteId, onFechar }: EditarAgenteModalProps) {
  const e = useProjetos();
  const modelos = useModelos();
  const celular = useCelular();
  const sora = agenteId === 'sora';
  const ag = sora ? undefined : e.agentes[agenteId];
  const [r, setR] = useState<RascunhoConstrutor | null>(() => sora
    ? { nome: e.sora.nome, funcao: 'Agente principal', descricaoCurta: '', cor: e.sora.cor, tipoMovimento: 'gira', ferramentas: [], instrucoes: '', frasesIniciais: [], tom: 'objetivo', modelo: null }
    : ag ? { id: ag.id, nome: ag.nome, funcao: ag.funcao, descricaoCurta: '', cor: ag.cor, tipoMovimento: ag.tipoMovimento, ferramentas: [...ag.ferramentas], instrucoes: ag.instrucoes, frasesIniciais: [], tom: 'objetivo', modelo: modelos.modelosPorAgente[ag.id] ?? null }
      : null);
  if (!r) return null;
  const valido = !!r.nome.trim() && (sora || !!r.funcao.trim());
  const salvar = () => {
    if (!valido) return;
    if (sora) atualizarSora({ nome: r.nome.trim(), cor: r.cor });
    else {
      atualizarAgente(agenteId, { nome: r.nome.trim(), funcao: r.funcao.trim(), cor: r.cor, tipoMovimento: r.tipoMovimento, ferramentas: r.ferramentas, instrucoes: r.instrucoes });
      if (r.modelo) definirModeloAgente(agenteId, r.modelo.provedor, r.modelo.modelo);
    }
    onFechar();
  };
  const titulo = sora ? `Personalizar ${e.sora.nome}` : `Editar ${ag?.nome ?? 'agente'}`;
  const descricao = sora ? 'Nome de exibição e cor da Sora.' : 'As mudanças aparecem na hora em todo o app.';
  const rodape = (
    <div className="bld-modal-actions">
      {sora && r.cor.toUpperCase() !== COR_SORA && <button type="button" className="bld-restore" onClick={() => setR({ ...r, cor: COR_SORA })}>Restaurar padrão</button>}
      <button type="button" onClick={onFechar}>Descartar</button>
      <button type="button" className="is-primary" disabled={!valido} onClick={salvar}>Salvar</button>
    </div>
  );
  const corpo = (
    <div className={`bld-edit ${sora ? 'bld-edit-sora' : ''}`}>
      <div className="bld-edit-form"><AgentConfigForm rascunho={r} onChange={setR} modo={sora ? 'sora' : 'agente'} /></div>
      {!sora && <div className="bld-edit-preview"><AgentPreview agente={r} /></div>}
    </div>
  );
  return celular
    ? <BottomSheet open onClose={onFechar} title={titulo} description={descricao} footer={rodape}>{corpo}</BottomSheet>
    : <Modal open onClose={onFechar} title={titulo} description={descricao} size="lg" className="bld-edit-modal" footer={rodape}>{corpo}</Modal>;
}

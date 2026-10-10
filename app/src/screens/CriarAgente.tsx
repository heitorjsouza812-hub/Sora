import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AgentConfigForm, AgentPreview, CreateConversation, type AbaConstrutor, type RascunhoConstrutor } from '../components/builder';
import '../components/builder/builder.css';
import { Modal } from '../components/overlay';
import { PALETA_AGENTES } from '../data/planejador';
import { definirModeloAgente, useModelos } from '../state/modelos';
import { removerAgente, salvarAgente, useProjetos } from '../state/projetos';

function novoRascunho(): RascunhoConstrutor { return { nome: '', funcao: 'Assistente', descricaoCurta: '', cor: PALETA_AGENTES[0], tipoMovimento: 'gira', ferramentas: [], instrucoes: '', frasesIniciais: [], tom: 'objetivo', modelo: null }; }
export default function CriarAgente() {
  const { id } = useParams<{ id: string }>();
  const projetos = useProjetos(); const modelos = useModelos(); const navigate = useNavigate();
  const existente = id ? projetos.agentes[id] : undefined;
  const inicial = useMemo<RascunhoConstrutor>(() => existente ? { id: existente.id, nome: existente.nome, funcao: existente.funcao, descricaoCurta: existente.funcao, cor: existente.cor, tipoMovimento: existente.tipoMovimento, ferramentas: [...existente.ferramentas], instrucoes: existente.instrucoes, frasesIniciais: [], tom: 'objetivo', modelo: modelos.modelosPorAgente[existente.id] ?? null } : novoRascunho(), [existente, modelos.modelosPorAgente]);
  const [rascunho, setRascunho] = useState(inicial); const [aba, setAba] = useState<AbaConstrutor>('criar'); const [salvo, setSalvo] = useState(!!existente); const [confirmar, setConfirmar] = useState(false);
  const alterar = (valor: RascunhoConstrutor) => { setRascunho(valor); setSalvo(false); };
  const salvar = () => { if (!rascunho.nome.trim() || !rascunho.funcao.trim()) return; const agente = salvarAgente({ id: rascunho.id, nome: rascunho.nome, funcao: rascunho.funcao, cor: rascunho.cor, tipoMovimento: rascunho.tipoMovimento, ferramentas: rascunho.ferramentas, instrucoes: rascunho.instrucoes }); if (rascunho.modelo) definirModeloAgente(agente.id, rascunho.modelo.provedor, rascunho.modelo.modelo); setRascunho(x => ({ ...x, id: agente.id })); setSalvo(true); if (!id) navigate(`/agentes/${agente.id}/editar`, { replace: true }); };
  const excluir = () => { if (!rascunho.id) return; removerAgente(rascunho.id); navigate('/agentes'); };
  const podeSalvar = !!rascunho.nome.trim() && !!rascunho.funcao.trim();
  return <main className="bld-page">
    <header className="bld-topbar"><Link className="bld-back" to="/agentes" aria-label="Voltar">←</Link><div className="bld-title"><strong>{rascunho.nome || 'Novo agente'}</strong><span>{salvo ? 'Salvo' : 'Rascunho'}</span></div><i /><button type="button" className="bld-discard" onClick={() => { setRascunho(inicial); setSalvo(!!existente); }}>Descartar</button><button type="button" className="bld-save" disabled={!podeSalvar || salvo} onClick={salvar}>{rascunho.id ? 'Salvar' : 'Criar agente'}</button></header>
    <nav className="bld-mobile-tabs" aria-label="Seções do construtor">{(['criar','configurar','previa'] as const).map(x => <button key={x} aria-selected={aba === x} onClick={() => setAba(x)}>{x === 'criar' ? 'Criar' : x === 'configurar' ? 'Configurar' : 'Prévia'}</button>)}</nav>
    <div className="bld-layout">
      <section className="bld-editor" hidden={aba === 'previa'}><div className="bld-tabs" role="tablist"><button role="tab" aria-selected={aba === 'criar'} onClick={() => setAba('criar')}>Criar</button><button role="tab" aria-selected={aba === 'configurar'} onClick={() => setAba('configurar')}>Configurar</button></div><div className="bld-editor-body">{aba === 'criar' ? <CreateConversation rascunho={rascunho} onChange={alterar} /> : <AgentConfigForm rascunho={rascunho} onChange={alterar} onExcluir={() => setConfirmar(true)} />}</div></section>
      <div className="bld-preview-wrap" hidden={aba !== 'previa' && typeof window !== 'undefined' && window.innerWidth < 768}><AgentPreview agente={rascunho} /></div>
    </div>
    <Modal open={confirmar} onClose={() => setConfirmar(false)} title={`Excluir ${rascunho.nome}?`} description="Esta ação não pode ser desfeita." size="sm" footer={<div className="bld-modal-actions"><button type="button" onClick={() => setConfirmar(false)}>Cancelar</button><button type="button" className="is-danger" onClick={excluir}>Excluir agente</button></div>}><p className="bld-modal-copy">O agente, seu histórico de conversa e suas associações serão removidos.</p></Modal>
  </main>;
}


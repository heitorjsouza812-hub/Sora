import { useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { AgentConfigForm, AgentPreview, type AbaConstrutor, type RascunhoConstrutor } from '../components/builder';
import '../components/builder/builder.css';
import { Modal } from '../components/overlay';
import { toast } from '../components/base';
import { definirModeloAgente, useModelos } from '../state/modelos';
import { removerAgente, salvarAgente, useProjetos } from '../state/projetos';

const vazio: RascunhoConstrutor = { nome: '', funcao: '', descricaoCurta: '', cor: '#56A8FF', tipoMovimento: 'gira', ferramentas: [], instrucoes: '', frasesIniciais: [], tom: 'objetivo', modelo: null };

export default function CriarAgente() {
  const { id } = useParams<{ id: string }>();
  const projetos = useProjetos(); const modelos = useModelos();
  const existente = id ? projetos.agentes[id] : undefined;
  const inicial = useMemo<RascunhoConstrutor>(() => existente ? { id: existente.id, nome: existente.nome, funcao: existente.funcao, descricaoCurta: existente.funcao, cor: existente.cor, tipoMovimento: existente.tipoMovimento, ferramentas: [...existente.ferramentas], instrucoes: existente.instrucoes, frasesIniciais: [], tom: 'objetivo', modelo: modelos.modelosPorAgente[existente.id] ?? null } : vazio, [existente, modelos.modelosPorAgente]);
  if (projetos.carregando) return null;
  if (!id || !existente) return <Navigate to="/bots" replace />;
  return <EditorBot key={existente.id} inicial={inicial} />;
}

function EditorBot({ inicial }: { inicial: RascunhoConstrutor }) {
  const navigate = useNavigate();
  const [rascunho, setRascunho] = useState(inicial); const [aba, setAba] = useState<AbaConstrutor>('configurar'); const [salvo, setSalvo] = useState(true); const [confirmar, setConfirmar] = useState(false);
  const alterar = (valor: RascunhoConstrutor) => { setRascunho(valor); setSalvo(false); };
  const salvar = async () => { if (!rascunho.id || !rascunho.nome.trim() || !rascunho.funcao.trim()) return; const agente = await salvarAgente({ id: rascunho.id, nome: rascunho.nome, funcao: rascunho.funcao, cor: rascunho.cor, tipoMovimento: rascunho.tipoMovimento, ferramentas: rascunho.ferramentas, instrucoes: rascunho.instrucoes }); if (rascunho.modelo) definirModeloAgente(agente.id, rascunho.modelo.provedor, rascunho.modelo.modelo); setRascunho(x => ({ ...x, id: agente.id })); setSalvo(true); toast({ mensagem: 'Bot salvo', tom: 'sucesso' }); };
  const excluir = () => { if (!rascunho.id) return; removerAgente(rascunho.id); navigate('/bots'); };
  const podeSalvar = !!rascunho.nome.trim() && !!rascunho.funcao.trim();
  return <main className="bld-page">
    <header className="bld-topbar"><Link className="bld-back" to={`/bots/${rascunho.id}`} aria-label="Voltar">←</Link><div className="bld-title"><strong>{rascunho.nome}</strong><span>{salvo ? 'Salvo' : 'Alterado'}</span></div><i /><button type="button" className="bld-discard" onClick={() => { setRascunho(inicial); setSalvo(true); }}>Descartar</button><button type="button" className="bld-save" disabled={!podeSalvar || salvo} onClick={() => { void salvar(); }}>Salvar</button></header>
    <nav className="bld-mobile-tabs" aria-label="Seções do editor">{(['configurar','previa'] as const).map(x => <button key={x} aria-selected={aba === x} onClick={() => setAba(x)}>{x === 'configurar' ? 'Configurar' : 'Prévia'}</button>)}</nav>
    <div className="bld-layout">
      <section className="bld-editor" hidden={aba === 'previa'}><div className="bld-tabs"><strong>Configurar bot</strong></div><div className="bld-editor-body"><AgentConfigForm rascunho={rascunho} onChange={alterar} onExcluir={() => setConfirmar(true)} /></div></section>
      <div className="bld-preview-wrap" hidden={aba !== 'previa' && typeof window !== 'undefined' && window.innerWidth < 768}><AgentPreview agente={rascunho} /></div>
    </div>
    <Modal open={confirmar} onClose={() => setConfirmar(false)} title={`Excluir ${rascunho.nome}?`} description="Esta ação não pode ser desfeita." size="sm" footer={<div className="bld-modal-actions"><button type="button" onClick={() => setConfirmar(false)}>Cancelar</button><button type="button" className="is-danger" onClick={excluir}>Excluir agente</button></div>}><p className="bld-modal-copy">O agente, seu histórico de conversa e suas associações serão removidos.</p></Modal>
  </main>;
}


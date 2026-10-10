// Telas PROVISÓRIAS: usadas só enquanto as definitivas não existem
// (screens/Projetos.tsx da Brisa; screens/Configuracoes.tsx e screens/CriarAgente.tsx do Forja).
// App.tsx troca para as definitivas automaticamente quando os arquivos aparecem.
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { rotuloFase } from '../components/layout/useSoraStatus';
import { SoraOrb } from '../components/mascot';
import { Modal } from '../components/overlay';
import { EditorAgente, type RascunhoEditor } from '../components/studio';
import { MessageComposer } from '../components/ui/MessageComposer';
import { PALETA_AGENTES } from '../data/planejador';
import { criarProjeto, estadoProjeto, limparTudo, salvarAgente, useAgora, useProjetos } from '../state/projetos';
import '../components/studio/studio.css';

export function EditorAgenteProvisorio() {
  const { id } = useParams();
  const e = useProjetos();
  const navigate = useNavigate();
  const a = id ? e.agentes[id] : undefined;
  const usadas = new Set(Object.values(e.agentes).map(x => x.cor.toUpperCase()));
  const inicial: RascunhoEditor = a
    ? { id: a.id, nome: a.nome, funcao: a.funcao, cor: a.cor, tipoMovimento: a.tipoMovimento, ferramentas: a.ferramentas, instrucoes: a.instrucoes }
    : { nome: '', funcao: '', cor: PALETA_AGENTES.find(c => !usadas.has(c)) ?? PALETA_AGENTES[0], tipoMovimento: 'gira', ferramentas: [], instrucoes: '' };
  return (
    <AppShell titulo={a ? `Editar ${a.nome}` : 'Criar agente'} acoes={<Link className="share-button" to="/agentes">Voltar</Link>}>
      <main className="ag-main">
        <EditorAgente key={a?.id ?? 'novo'} inicial={inicial} comDescricao={!a} coresEmUso={[...usadas]}
          onSalvar={r => { const s = salvarAgente(r); navigate(`/chat/${s.id}`); }}
          onDescartar={() => navigate('/agentes')} />
      </main>
    </AppShell>
  );
}

export function ConfiguracoesProvisoria() {
  const navigate = useNavigate();
  const [confirmar, setConfirmar] = useState(false);
  return (
    <AppShell titulo="Configurações">
      <main className="gallery-screen">
        <header className="gallery-head"><div><h1>Configurações</h1><p>Conta</p></div></header>
        <section className="card settings-danger">
          <div><strong>Apagar todos os dados</strong><p>Remove chats, projetos, agentes e personalizações deste navegador.</p></div>
          <button type="button" className="st-btn gestao-danger" onClick={() => setConfirmar(true)}>Apagar todos os dados</button>
        </section>
      </main>
      <Modal open={confirmar} onClose={() => setConfirmar(false)} size="sm" title="Apagar todos os dados?"
        description="Todos os chats, projetos e agentes serão apagados. Não dá para desfazer."
        footer={<div className="gestao-footer">
          <button type="button" className="st-btn-ghost" onClick={() => setConfirmar(false)}>Cancelar</button>
          <button type="button" className="st-btn gestao-danger" onClick={() => { limparTudo(); setConfirmar(false); navigate('/'); }}>Apagar tudo</button>
        </div>}>
        <p className="settings-note">A Sora continua aqui — só o que você criou é apagado.</p>
      </Modal>
    </AppShell>
  );
}

export function ProjetosProvisoria() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const projetos = e.projetos.filter(p => p.tipo === 'projeto');
  return (
    <AppShell titulo="Projetos">
      <main className="gallery-screen">
        <header className="gallery-head"><div><h1>Projetos</h1><p>Descreva o projeto: a {e.sora.nome} monta o plano e cria a equipe inteira.</p></div></header>
        <div className="projects-new">
          <MessageComposer placeholder="Novo projeto: descreva o que a equipe deve fazer…" compact
            onSend={t => { const p = criarProjeto(t, undefined, { tipo: 'projeto' }); navigate(`/projeto/${p.id}`); }} />
        </div>
        <div className="gallery-grid">
          {projetos.map(p => (
            <Link key={p.id} to={`/projeto/${p.id}`} className="gallery-card card">
              <strong>{p.titulo}</strong>
              <div className="project-avatars">{p.agenteIds.map(id => e.agentes[id] && <SoraOrb key={id} size={28} color={e.agentes[id].cor} glow={false} decorative />)}</div>
              <small>{rotuloFase[estadoProjeto(e, p, agora).fase]} · {new Date(p.criadoEm).toLocaleDateString('pt-BR')}</small>
            </Link>
          ))}
        </div>
      </main>
    </AppShell>
  );
}

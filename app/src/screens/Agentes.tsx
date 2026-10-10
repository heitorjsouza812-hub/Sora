// Aba "Agentes": estúdio para criar e editar agentes individuais.
// Esquerda: todos os agentes (avulsos + de cada equipe) e "Novo agente". Centro: editor com prévia ao vivo.
import { useState, type CSSProperties } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { EditorAgente, type RascunhoEditor } from '../components/studio';
import { PALETA_AGENTES } from '../data/planejador';
import {
  agentesAvulsos, estadoAgente, removerAgente, salvarAgente, useAgora, useProjetos, type AgenteSora,
} from '../state/projetos';
import '../components/studio/studio.css';

const vazio = (coresEmUso: string[]): RascunhoEditor => {
  const usadas = new Set(coresEmUso.map(c => c.toUpperCase()));
  return { nome: '', funcao: '', cor: PALETA_AGENTES.find(c => !usadas.has(c)) ?? PALETA_AGENTES[0], tipoMovimento: 'gira', ferramentas: [], instrucoes: '' };
};
const paraRascunho = (a: AgenteSora): RascunhoEditor => ({
  id: a.id, nome: a.nome, funcao: a.funcao, cor: a.cor, tipoMovimento: a.tipoMovimento, ferramentas: a.ferramentas, instrucoes: a.instrucoes,
});

function ItemAgente({ a, ativo, rotulo, onClick }: { a: AgenteSora; ativo: boolean; rotulo: string; onClick: () => void }) {
  return (
    <button type="button" className={`ag-item ${ativo ? 'is-on' : ''}`} style={{ '--agent': a.cor } as CSSProperties} onClick={onClick}>
      <SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} state="idle" glow={false} title={a.nome} />
      <span><strong>{a.nome}</strong><small>{rotulo}</small></span>
    </button>
  );
}

export default function Agentes() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [confirmarExclusao, setConfirmar] = useState(false);
  const selecionado = params.get('agente');
  const ag = selecionado && selecionado !== 'novo' ? e.agentes[selecionado] : undefined;
  const coresEmUso = Object.values(e.agentes).map(a => a.cor);
  const avulsos = agentesAvulsos(e);
  const grupos = e.projetos
    .map(p => ({ p, ags: p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a && a.criadoEm <= agora) }))
    .filter(g => g.ags.length);
  const selecionar = (id: string) => { setConfirmar(false); setParams({ agente: id }); };
  const total = avulsos.length + grupos.reduce((n, g) => n + g.ags.length, 0);

  return (
    <AppShell title="Agentes">
      <div className="ag-studio">
        <aside className="ag-list" aria-label="Seus agentes">
          <button type="button" className="ag-new" onClick={() => selecionar('novo')}><span>+</span>Novo agente</button>
          {total === 0 && <p className="ag-empty">Você ainda não tem agentes. Crie um aqui ou peça uma equipe para a Sora na aba Equipes.</p>}
          {avulsos.length > 0 && <p className="eyebrow ag-group">Avulsos</p>}
          {avulsos.map(a => <ItemAgente key={a.id} a={a} ativo={a.id === selecionado} rotulo={a.funcao} onClick={() => selecionar(a.id)} />)}
          {grupos.map(({ p, ags }) => (
            <div key={p.id}>
              <p className="eyebrow ag-group" title={p.titulo}>{p.titulo}</p>
              {ags.map(a => <ItemAgente key={a.id} a={a} ativo={a.id === selecionado} rotulo={estadoAgente(e, a.id, agora).rotulo || a.funcao} onClick={() => selecionar(a.id)} />)}
            </div>
          ))}
        </aside>

        <main className="ag-main">
          <header className="ag-head">
            <h1>{ag ? `Editar ${ag.nome}` : 'Novo agente'}</h1>
            <p>{ag ? (ag.avulso ? 'Agente avulso · converse com ele direto pelo chat.' : 'Faz parte de uma equipe. As mudanças aparecem na hora em todo o app.') : 'Descreva o agente para a Sora preencher, ou monte você mesmo.'}</p>
          </header>
          <EditorAgente
            key={ag?.id ?? 'novo'}
            inicial={ag ? paraRascunho(ag) : vazio(coresEmUso)}
            comDescricao={!ag}
            coresEmUso={coresEmUso}
            onSalvar={r => { const novo = salvarAgente(r); selecionar(novo.id); }}
            onDescartar={() => { if (!ag) setParams({}); }}
            extras={ag && <>
              <button type="button" className="st-btn-ghost" onClick={() => navigate(`/chat/${ag.id}`)}>Conversar</button>
              {ag.avulso && (confirmarExclusao
                ? <button type="button" className="st-btn-ghost st-btn-danger" onClick={() => { removerAgente(ag.id); setParams({}); }}>Confirmar exclusão</button>
                : <button type="button" className="st-btn-ghost st-btn-danger" onClick={() => setConfirmar(true)}>Excluir</button>)}
            </>}
          />
        </main>
      </div>
    </AppShell>
  );
}

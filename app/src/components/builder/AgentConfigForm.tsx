import { Link } from 'react-router-dom';
import type { CSSProperties } from 'react';
import { COR_SORA, MOVIMENTOS, PALETA_AGENTES } from '../../data/planejador';
import { modelosAtivos, useModelos, type EscolhaModelo, type ProvedorModeloId } from '../../state/modelos';
import { SoraOrb } from '../mascot';
import type { RascunhoConstrutor } from './types';

const FERRAMENTAS = ['Perplexity', 'Notion', 'Google Drive', 'Figma', 'Canva', 'GitHub', 'Gmail', 'Google Agenda', 'Planilhas Google'];
export interface AgentConfigFormProps {
  rascunho: RascunhoConstrutor;
  onChange: (valor: RascunhoConstrutor) => void;
  onExcluir?: () => void;
  /** 'sora': só nome de exibição e cor (a Sora não tem função, movimento nem ferramentas) */
  modo?: 'agente' | 'sora';
}

export function AgentConfigForm({ rascunho: r, onChange, onExcluir, modo = 'agente' }: AgentConfigFormProps) {
  const modelos = useModelos();
  const set = <K extends keyof RascunhoConstrutor>(k: K, valor: RascunhoConstrutor[K]) => onChange({ ...r, [k]: valor });
  const opcoesModelo = modelosAtivos(modelos).map(({ provedor, modelo, definicao }) => ({ p: provedor, m: modelo.modelo, label: `${definicao.nome} · ${modelo.modelo}` }));
  const valorModelo = r.modelo ? `${r.modelo.provedor}::${r.modelo.modelo}` : '';
  if (modo === 'sora') {
    return <div className="bld-config bld-config-sora">
      <div className="bld-section-grid">
        <label className="bld-wide"><span>Nome de exibição</span><input value={r.nome} maxLength={24} onChange={e => set('nome', e.target.value)} /></label>
        <div className="bld-wide"><span className="bld-label">Cor</span><div className="bld-swatches">{[COR_SORA, ...PALETA_AGENTES].map(c => <button key={c} type="button" className={r.cor.toUpperCase() === c ? 'is-on' : ''} style={{ '--choice': c } as CSSProperties} onClick={() => set('cor', c)} aria-label={`Cor ${c}`} aria-pressed={r.cor.toUpperCase() === c} />)}</div></div>
      </div>
    </div>;
  }
  return <div className="bld-config">
    <details open><summary>Identidade<span>Nome, função e descrição</span></summary><div className="bld-section-grid">
      <label><span>Nome</span><input value={r.nome} maxLength={24} onChange={e => set('nome', e.target.value)} /></label>
      <label><span>Função</span><input value={r.funcao} maxLength={48} onChange={e => set('funcao', e.target.value)} /></label>
      <label className="bld-wide"><span>Descrição curta</span><input value={r.descricaoCurta} maxLength={100} onChange={e => set('descricaoCurta', e.target.value)} placeholder="Como este agente ajuda" /></label>
    </div></details>
    <details open><summary>Aparência<span>Cor e movimento do orb</span></summary><div className="bld-section-grid">
      <div className="bld-wide"><span className="bld-label">Cor</span><div className="bld-swatches">{PALETA_AGENTES.map(c => <button key={c} type="button" className={r.cor.toUpperCase() === c ? 'is-on' : ''} style={{ '--choice': c } as CSSProperties} onClick={() => set('cor', c)} aria-label={`Cor ${c}`} />)}<label className="bld-hex"><input type="color" value={r.cor} onChange={e => set('cor', e.target.value)} /><input value={r.cor} onChange={e => /^#[0-9a-f]{0,6}$/i.test(e.target.value) && set('cor', e.target.value)} aria-label="Cor hexadecimal" /></label></div></div>
      <div className="bld-wide"><span className="bld-label">Movimento</span><div className="bld-moves">{MOVIMENTOS.map(m => <button type="button" key={m.id} className={r.tipoMovimento === m.id ? 'is-on' : ''} onClick={() => set('tipoMovimento', m.id)}><SoraOrb size={38} color={r.cor} state="working" movimento={m.id} seed={m.id.length} decorative /><span><strong>{m.nome}</strong><small>{m.descricao}</small></span></button>)}</div></div>
    </div></details>
    <details open><summary>Comportamento<span>Instruções, tom e início do chat</span></summary><div className="bld-section-grid">
      <label className="bld-wide"><span>Instruções</span><textarea rows={8} value={r.instrucoes} onChange={e => set('instrucoes', e.target.value)} placeholder="Objetivo, processo, limites e formato das respostas…" /></label>
      <label><span>Tom</span><select value={r.tom} onChange={e => set('tom', e.target.value as RascunhoConstrutor['tom'])}><option value="objetivo">Objetivo</option><option value="amigavel">Amigável</option><option value="criativo">Criativo</option><option value="tecnico">Técnico</option></select></label>
      <label><span>Frase inicial sugerida</span><input value={r.frasesIniciais[0] ?? ''} onChange={e => set('frasesIniciais', [e.target.value])} placeholder="Ex.: Analise estas referências" /></label>
    </div></details>
    <details><summary>Modelo<span>Provedor usado por este agente</span></summary><div className="bld-section-grid"><label className="bld-wide"><span>Modelo de IA</span><select value={valorModelo} onChange={e => { const [provedor, modelo] = e.target.value.split('::'); set('modelo', provedor ? { provedor: provedor as ProvedorModeloId, modelo } as EscolhaModelo : null); }}><option value="">Usar padrão dos novos agentes</option>{opcoesModelo.map(x => <option key={`${x.p}::${x.m}`} value={`${x.p}::${x.m}`}>{x.label}</option>)}</select>{!opcoesModelo.length && <small>Nenhum provedor conectado. <Link to="/configuracoes">Conectar modelos</Link></small>}</label></div></details>
    <details><summary>Ferramentas<span>O que ele pode usar</span></summary><div className="bld-tool-grid">{FERRAMENTAS.map(f => <label key={f}><input type="checkbox" checked={r.ferramentas.includes(f)} onChange={e => set('ferramentas', e.target.checked ? [...r.ferramentas, f] : r.ferramentas.filter(x => x !== f))} /><span>{f}</span></label>)}</div></details>
    {r.id && <details className="bld-danger"><summary>Zona de perigo<span>Ações irreversíveis</span></summary><div><p>Excluir remove o agente e a conversa associada.</p><button type="button" onClick={onExcluir}>Excluir agente</button></div></details>}
  </div>;
}


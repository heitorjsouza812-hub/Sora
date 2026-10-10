// Editor de agente: prévia grande do orb ao vivo + Nome, Função, Cor, Movimento, Ferramentas,
// Instruções. Usado no estúdio "Agentes" (página) e no painel "Editar agente" (em qualquer lugar).
import { useState, type CSSProperties, type ReactNode } from 'react';
import { COR_SORA, type RascunhoAgente } from '../../data/planejador';
import { SoraOrb } from '../mascot';
import { CriarPorDescricao } from './CriarPorDescricao';
import { SeletorCor } from './SeletorCor';
import { SeletorFerramentas } from './SeletorFerramentas';
import { SeletorMovimento } from './SeletorMovimento';
import './studio.css';

export type RascunhoEditor = RascunhoAgente & { id?: string };

export interface EditorAgenteProps {
  inicial: RascunhoEditor;
  /** 'sora': só nome de exibição e cor (com "Restaurar padrão") */
  modo?: 'agente' | 'sora';
  variante?: 'pagina' | 'painel';
  /** cores já usadas por outros agentes (marcadas na paleta) */
  coresEmUso?: string[];
  /** mostra o campo "Descreva o agente que você quer…" */
  comDescricao?: boolean;
  onSalvar: (r: RascunhoEditor) => void;
  onDescartar: () => void;
  /** ações extras no rodapé (ex.: Conversar, Excluir) */
  extras?: ReactNode;
}

const igual = (a: RascunhoEditor, b: RascunhoEditor) => JSON.stringify(a) === JSON.stringify(b);

export function EditorAgente({ inicial, modo = 'agente', variante = 'pagina', coresEmUso, comDescricao, onSalvar, onDescartar, extras }: EditorAgenteProps) {
  const [r, setR] = useState<RascunhoEditor>(inicial);
  const [preenchidoPelaSora, setPreenchido] = useState(false);
  const set = <K extends keyof RascunhoEditor>(k: K, v: RascunhoEditor[K]) => setR(x => ({ ...x, [k]: v }));
  const sora = modo === 'sora';
  const sujo = !igual(r, inicial);
  const valido = r.nome.trim().length > 0 && (sora || r.funcao.trim().length > 0);
  const novo = !r.id && !sora;
  const orbSize = variante === 'pagina' ? 220 : 150;

  return (
    <div className={`st-editor st-${variante}`} style={{ '--agent': r.cor } as CSSProperties}>
      <div className="st-preview">
        <div className="st-preview-orb">
          <SoraOrb size={orbSize} color={r.cor} movimento={sora ? 'gira' : r.tipoMovimento} state={sora ? 'idle' : 'working'} title={r.nome || 'Prévia'} />
        </div>
        <strong className="st-preview-name">{r.nome || 'Sem nome'}</strong>
        <span className="st-preview-role">{sora ? 'Agente principal' : r.funcao || 'Função'}</span>
        <span className="st-live"><i />Prévia ao vivo</span>
      </div>

      <div className="st-form-col">
      {comDescricao && novo && (
        <section className="st-field st-describe-box">
          <span className="st-label">Criar por conversa</span>
          <CriarPorDescricao onPreencher={x => { setR(v => ({ ...v, ...x })); setPreenchido(true); }} />
          {preenchidoPelaSora && <small className="st-hint st-hint-ok">A Sora preencheu o formulário. Ajuste o que quiser e salve.</small>}
        </section>
      )}
      <form className="st-form" onSubmit={ev => { ev.preventDefault(); if (valido) onSalvar({ ...r, nome: r.nome.trim(), funcao: r.funcao.trim() }); }}>
        <div className="st-row">
          <label className="st-field">
            <span className="st-label">{sora ? 'Nome de exibição' : 'Nome'}</span>
            <input className="st-input" value={r.nome} maxLength={24} placeholder="Ex.: Atlas" onChange={ev => set('nome', ev.target.value)} />
          </label>
          {!sora && (
            <label className="st-field">
              <span className="st-label">Função</span>
              <input className="st-input" value={r.funcao} maxLength={40} placeholder="Ex.: Pesquisa e referências" onChange={ev => set('funcao', ev.target.value)} />
            </label>
          )}
        </div>

        <section className="st-field">
          <span className="st-label">Cor
            {sora && r.cor.toUpperCase() !== COR_SORA && <button type="button" className="st-link" onClick={() => set('cor', COR_SORA)}>Restaurar padrão</button>}
          </span>
          <SeletorCor valor={r.cor} onChange={c => set('cor', c)} incluirSora={sora} emUso={sora ? [] : coresEmUso?.filter(c => c.toUpperCase() !== inicial.cor.toUpperCase())} />
        </section>

        {!sora && (
          <>
            <section className="st-field">
              <span className="st-label">Movimento</span>
              <SeletorMovimento valor={r.tipoMovimento} cor={r.cor} onChange={m => set('tipoMovimento', m)} />
            </section>
            <section className="st-field">
              <span className="st-label">Ferramentas</span>
              <SeletorFerramentas valor={r.ferramentas} onChange={f => set('ferramentas', f)} />
            </section>
            <label className="st-field">
              <span className="st-label">Instruções</span>
              <textarea className="st-input st-textarea" rows={5} value={r.instrucoes}
                placeholder="Como este agente deve trabalhar? Tom, regras, o que entregar…" onChange={ev => set('instrucoes', ev.target.value)} />
            </label>
          </>
        )}

        <footer className="st-actions">
          {extras}
          <span className="st-spacer" />
          <button type="button" className="st-btn-ghost" onClick={() => { setR(inicial); onDescartar(); }}>Descartar</button>
          <button type="submit" className="st-btn" disabled={!valido || (!sujo && !novo)}>{novo ? 'Criar agente' : 'Salvar'}</button>
        </footer>
      </form>
      </div>
    </div>
  );
}

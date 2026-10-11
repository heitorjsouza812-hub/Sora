import { useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { rotuloFase } from '../layout/useSoraStatus';
import { normalizar } from '../projetos/util';
import { definirIlhaPrefs, useIlha, useIlhaPrefs, type ResumoProjetoIlha } from './ilhaEstado';
import './ilha-partes.css';

type Opcao = { id: string | null; projeto?: ResumoProjetoIlha };

export function SeletorProjeto({ onEscolhido }: { onEscolhido: () => void }) {
  const { projetos } = useIlha();
  const prefs = useIlhaPrefs();
  const [busca, setBusca] = useState('');
  const [ativo, setAtivo] = useState(0);
  const opcoesRef = useRef<Array<HTMLButtonElement | null>>([]);
  const mostraBusca = projetos.length > 6;
  const termo = normalizar(busca.trim());
  const filtrados = useMemo(
    () => projetos.filter((projeto) => !termo || normalizar(`${projeto.titulo} ${rotuloFase[projeto.fase] ?? projeto.fase}`).includes(termo)),
    [projetos, termo],
  );
  const opcoes: Opcao[] = [{ id: null }, ...filtrados.map((projeto) => ({ id: projeto.id, projeto }))];
  const atual = Math.min(ativo, Math.max(0, opcoes.length - 1));

  const escolher = (id: string | null) => {
    definirIlhaPrefs({ projetoId: id });
    onEscolhido();
  };
  const tecla = (evento: KeyboardEvent<HTMLDivElement>) => {
    const ultimo = opcoes.length - 1;
    let proximo = atual;
    if (evento.key === 'ArrowDown') proximo = atual === ultimo ? 0 : atual + 1;
    else if (evento.key === 'ArrowUp') proximo = atual === 0 ? ultimo : atual - 1;
    else if (evento.key === 'Home') proximo = 0;
    else if (evento.key === 'End') proximo = ultimo;
    else if (evento.key === 'Enter' || evento.key === ' ') {
      evento.preventDefault();
      escolher(opcoes[atual]?.id ?? null);
      return;
    } else return;
    evento.preventDefault();
    setAtivo(proximo);
    opcoesRef.current[proximo]?.focus();
  };

  return (
    <section className="ilha-seletor" aria-labelledby="ilha-seletor-titulo">
      <header><h2 id="ilha-seletor-titulo">Escolher projeto</h2><p>Defina qual equipe aparece na Ilha da Sora.</p></header>
      {mostraBusca && <label className="ilha-seletor__busca"><span>Buscar projeto</span><input value={busca} onChange={(evento) => { setBusca(evento.target.value); setAtivo(0); }} placeholder="Buscar projeto…" /></label>}
      <div className="ilha-seletor__lista" role="listbox" aria-label="Projetos" onKeyDown={tecla}>
        {opcoes.map((opcao, indice) => {
          const selecionado = prefs.projetoId === opcao.id;
          if (!opcao.projeto) return (
            <button key="automatico" ref={(el) => { opcoesRef.current[indice] = el; }} type="button" role="option" aria-selected={selecionado} tabIndex={indice === atual ? 0 : -1}
              className="ilha-projeto-opcao ilha-projeto-opcao--auto" onFocus={() => setAtivo(indice)} onClick={() => escolher(null)}>
              <span className="ilha-projeto-opcao__marca" aria-hidden="true">✦</span><span><strong>Automático — projeto aberto</strong><small>A Sora acompanha o projeto atual ou o que estiver rodando.</small></span>
            </button>
          );
          const projeto = opcao.projeto;
          return (
            <button key={projeto.id} ref={(el) => { opcoesRef.current[indice] = el; }} type="button" role="option" aria-selected={selecionado} tabIndex={indice === atual ? 0 : -1}
              className="ilha-projeto-opcao" onFocus={() => setAtivo(indice)} onClick={() => escolher(projeto.id)}>
              <span className="ilha-projeto-opcao__texto"><strong>{projeto.titulo}</strong><small>{rotuloFase[projeto.fase] ?? projeto.fase}</small></span>
              <span className="ilha-projeto-opcao__cores" aria-label={`${projeto.total} agentes`}>
                {projeto.cores.slice(0, 5).map((cor, i) => <i key={`${cor}-${i}`} style={{ background: cor }} />)}
              </span>
              <span className="ilha-projeto-opcao__status">{projeto.trabalhando} trabalhando</span>
              <span className="ilha-projeto-opcao__progresso"><i style={{ width: `${projeto.progresso}%` }} /><small>{projeto.progresso}%</small></span>
            </button>
          );
        })}
        {termo && !filtrados.length && <p className="ilha-seletor__vazio">Nenhum projeto encontrado.</p>}
      </div>
    </section>
  );
}

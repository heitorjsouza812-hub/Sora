// Tela PROJETOS: pedido grande no topo (a Sora monta a equipe) + grade de projetos com filtro e busca.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import {
  CartaoProjeto, CompositorProjeto, EstadoVazio, FILTROS, grupoDaFase, normalizar, type FiltroProjetos,
} from '../components/projetos';
import { criarProjeto, estadoProjeto, useAgora, useProjetos } from '../state/projetos';
import '../components/projetos/projetos.css';

export default function Projetos() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const [pensando, setPensando] = useState(false);
  const [filtro, setFiltro] = useState<FiltroProjetos>('todos');
  const [busca, setBusca] = useState('');
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const enviar = (pedido: string) => {
    if (pensando) return;
    const p = criarProjeto(pedido, undefined, { tipo: 'projeto' });
    setPensando(true);
    // um instante de "pensando" aqui (VoiceBeam em processing) antes de abrir o chat do projeto
    timer.current = window.setTimeout(() => navigate(`/projeto/${p.id}`), 900);
  };

  const projetos = e.projetos.filter((p) => p.tipo === 'projeto');
  const comFase = projetos.map((p) => ({ p, grupo: grupoDaFase(estadoProjeto(e, p, agora).fase) }));
  const contagem = (f: FiltroProjetos) => f === 'todos' ? comFase.length : comFase.filter((x) => x.grupo === f).length;
  const termo = normalizar(busca.trim());
  const visiveis = comFase
    .filter((x) => filtro === 'todos' || x.grupo === filtro)
    .filter((x) => !termo || normalizar(`${x.p.titulo} ${x.p.pedido}`).includes(termo))
    .map((x) => x.p);

  return (
    <AppShell titulo="Projetos">
      <main className="pj-screen">
        <CompositorProjeto nomeSora={e.sora.nome} corSora={e.sora.cor} pensando={pensando} onEnviar={enviar} />

        <section className="pj-lista" aria-labelledby="pj-lista-titulo">
          <div className="pj-lista-topo">
            <h2 id="pj-lista-titulo">Seus projetos <span>{projetos.length}</span></h2>
            {projetos.length > 0 && (
              <div className="pj-controles">
                <div className="pj-filtros" role="group" aria-label="Filtrar projetos">
                  {FILTROS.map((f) => (
                    <button key={f.id} type="button" aria-pressed={filtro === f.id}
                      className={filtro === f.id ? 'is-on' : undefined} onClick={() => setFiltro(f.id)}>
                      {f.rotulo}<span aria-hidden="true">{contagem(f.id)}</span>
                    </button>
                  ))}
                </div>
                <label className="pj-busca">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
                  <span className="pj-sr">Buscar projetos</span>
                  <input type="search" placeholder="Buscar projetos" value={busca} onChange={(ev) => setBusca(ev.target.value)} />
                </label>
              </div>
            )}
          </div>

          {projetos.length === 0
            ? <EstadoVazio corSora={e.sora.cor} nomeSora={e.sora.nome} />
            : visiveis.length === 0
              ? <EstadoVazio corSora={e.sora.cor} nomeSora={e.sora.nome} busca onLimpar={() => { setBusca(''); setFiltro('todos'); }} />
              : <div className="pj-grade">
                {visiveis.map((p) => <CartaoProjeto key={p.id} e={e} projeto={p} agora={agora} />)}
              </div>}
        </section>
      </main>
    </AppShell>
  );
}

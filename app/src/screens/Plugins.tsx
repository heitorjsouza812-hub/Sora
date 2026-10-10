import type { CSSProperties } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { PluginMark } from '../components/ui/PluginMark';
import { plugins } from '../data/mock';
import { alternarPlugin, useProjetos } from '../state/projetos';

export default function Plugins() {
  const { pluginsConectados } = useProjetos();
  const conectado = (nome: string) => pluginsConectados.includes(nome);
  const featured = plugins.filter((plugin) => plugin.destaque);
  return <AppShell titulo="Plugins">
    <main className="plugins-screen">
      <header><h1>Conecte suas ferramentas favoritas.</h1><p>Mais de 1.000 plugins para os seus agentes usarem.</p></header>
      <p className="sr-only" role="status" aria-live="polite">{pluginsConectados.length} plugins conectados</p>
      <div className="plugins-layout">
        <section className="featured" aria-labelledby="destaques"><p className="eyebrow" id="destaques">Em destaque</p>{featured.map((plugin) => <article className="featured-plugin card" key={plugin.id}>
          <span className="plugin-box"><PluginMark nome={plugin.nome} cor={plugin.cor} path={plugin.path} size={34} /></span>
          <div><strong>{plugin.nome}</strong><small>{plugin.descricao}</small></div>
          <button type="button" aria-pressed={conectado(plugin.nome)} className={conectado(plugin.nome) ? 'connected-button' : 'connect-button'} onClick={() => alternarPlugin(plugin.nome)}>{conectado(plugin.nome) ? '● Conectado' : 'Conectar'}</button>
        </article>)}</section>
        <section className="plugin-gallery" aria-label="Todos os plugins">{plugins.map((plugin) => (
          <button type="button" aria-pressed={conectado(plugin.nome)} className={`plugin-tile card ${conectado(plugin.nome) ? 'is-connected' : ''}`} key={plugin.id}
            style={{ '--brand': plugin.cor } as CSSProperties} onClick={() => alternarPlugin(plugin.nome)}>
            <PluginMark nome={plugin.nome} cor={plugin.cor} path={plugin.path} size={42} />
            <strong>{plugin.nome}</strong><small>{conectado(plugin.nome) ? '● Conectado' : plugin.categoria}</small>
          </button>
        ))}</section>
      </div>
    </main>
  </AppShell>;
}

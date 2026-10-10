import { useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { PluginMark } from '../components/ui/PluginMark';
import { plugins } from '../data/mock';

export default function Plugins() {
  const [connected, setConnected] = useState(() => new Set(plugins.filter((plugin) => plugin.conectado).map((plugin) => plugin.id)));
  const featured = plugins.filter((plugin) => plugin.destaque);
  const toggle = (id: string) => setConnected((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  return <AppShell title="Plugins">
    <main className="plugins-screen">
      <header><h1>Conecte suas ferramentas favoritas.</h1><p>Mais de 1.000 plugins para os seus agentes usarem.</p></header>
      <div className="plugins-layout">
        <section className="featured"><p className="eyebrow">Em destaque</p>{featured.map((plugin) => <article className="featured-plugin card" key={plugin.id}>
          <span className="plugin-box"><PluginMark nome={plugin.nome} cor={plugin.cor} path={plugin.path} size={34} /></span>
          <div><strong>{plugin.nome}</strong><small>{plugin.descricao}</small></div>
          <button className={connected.has(plugin.id) ? 'connected-button' : 'connect-button'} onClick={() => toggle(plugin.id)}>{connected.has(plugin.id) ? '● Conectado' : 'Conectar'}</button>
        </article>)}</section>
        <section className="plugin-gallery" aria-label="Todos os plugins">{plugins.map((plugin) => <article className="plugin-tile card" key={plugin.id} style={{ '--brand': plugin.cor } as React.CSSProperties}><PluginMark nome={plugin.nome} cor={plugin.cor} path={plugin.path} size={42} /><strong>{plugin.nome}</strong><small>{plugin.categoria}</small></article>)}</section>
      </div>
    </main>
  </AppShell>;
}


// Cartão de entrega genérico (qualquer equipe): links, imagens, textos ou calendário. Tudo vem do conteúdo
// real da entrega; o que não veio aparece como estado vazio, nunca como exemplo.
import type { CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada } from '../../state/projetos';
import { eventosDaEntrega, linksDaEntrega, rotuloDoLink, textosDaEntrega } from './conteudoDaEntrega';
import { ImagensEntrega } from './ImagensEntrega';
import { imagensDaEntrega } from './imagensDaEntrega';

const LIMITE_LINKS = 4, LIMITE_TEXTO = 5, LIMITE_DATAS = 6;

export function EntregaCard({ entrega, agente }: { entrega: EntregaGerada; agente: AgenteSora }) {
  const links = entrega.tipo === 'links' ? linksDaEntrega(entrega) : [];
  const textos = entrega.tipo === 'texto' ? textosDaEntrega(entrega) : [];
  const eventos = entrega.tipo === 'calendario' ? eventosDaEntrega(entrega) : [];
  return (
    <article className="delivery-card card" style={{ '--agent': agente.cor } as CSSProperties}>
      <header><i aria-hidden="true" /><h3>{entrega.titulo}</h3><span>{agente.nome} · {entrega.resumo}</span></header>
      {entrega.tipo === 'links' && (links.length
        ? links.slice(0, LIMITE_LINKS).map(l => { const r = rotuloDoLink(l); return (
          <a key={l.url} className="delivery-link" href={l.url} target="_blank" rel="noreferrer" title={l.titulo === l.dominio ? l.url : `${l.titulo} · ${l.url}`}>
            {/* espaço não separável: a seta não fica sozinha numa linha; a quebra cai dentro do caminho */}
            <span>{`↗ ${r.principal}`}</span>{r.secundario && <small>{r.secundario}</small>}
          </a>); })
        : <p className="delivery-text">Esta entrega não trouxe links.</p>)}
      {/* imagens reais (captura, peça gerada) de qualquer tipo de entrega; sem imagem, nada inventado */}
      <ImagensEntrega entrega={entrega} limite={3} />
      {entrega.tipo === 'imagem' && !imagensDaEntrega(entrega).length && <p className="delivery-text">Esta entrega não trouxe imagem.</p>}
      {entrega.tipo === 'calendario' && (eventos.length
        ? <ul className="delivery-items delivery-dates">{eventos.slice(0, LIMITE_DATAS).map((ev, i) => <li key={`${ev.quando}-${i}`}><b>{ev.quando}</b> {ev.titulo}</li>)}</ul>
        : <p className="delivery-text">Esta entrega não trouxe datas.</p>)}
      {entrega.tipo === 'calendario' && eventos.length > LIMITE_DATAS && <small className="delivery-more">+{eventos.length - LIMITE_DATAS} datas na revisão</small>}
      {entrega.tipo === 'texto' && (textos.length
        ? <ul className="delivery-items">{textos.slice(0, LIMITE_TEXTO).map((t, i) => <li key={i}>{t}</li>)}</ul>
        : <p className="delivery-text">Esta entrega não trouxe texto.</p>)}
    </article>
  );
}

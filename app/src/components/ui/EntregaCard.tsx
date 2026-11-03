// Cartão de entrega genérico (qualquer equipe): links, imagens, textos ou calendário.
import type { CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada } from '../../state/projetos';
import { Calendar } from './Calendar';
import { ImagensEntrega } from './ImagensEntrega';
import { imagensDaEntrega } from './imagensDaEntrega';

export function EntregaCard({ entrega, agente }: { entrega: EntregaGerada; agente: AgenteSora }) {
  return (
    <article className="delivery-card card" style={{ '--agent': agente.cor } as CSSProperties}>
      <header><i aria-hidden="true" /><h3>{entrega.titulo}</h3><span>{agente.nome} · {entrega.resumo}</span></header>
      {entrega.tipo === 'links' && (entrega.links?.length
        ? entrega.links.map(l => <a key={l.titulo} href={`https://${l.dominio}`} target="_blank" rel="noreferrer">↗ {l.titulo} <small>{l.dominio}</small></a>)
        : <p className="delivery-text">{entrega.resumo} organizadas por {agente.nome}.</p>)}
      {/* imagens reais (captura, peça gerada) de qualquer tipo de entrega; sem imagem, nada inventado */}
      <ImagensEntrega entrega={entrega} limite={3} />
      {entrega.tipo === 'imagem' && !imagensDaEntrega(entrega).length && <p className="delivery-text">Esta entrega não trouxe imagem.</p>}
      {entrega.tipo === 'calendario' && <Calendar compact />}
      {entrega.tipo === 'texto' && <ul className="delivery-items">{(entrega.itens ?? [entrega.resumo]).slice(0, 5).map(i => <li key={i}>{i}</li>)}</ul>}
    </article>
  );
}

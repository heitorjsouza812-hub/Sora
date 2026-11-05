// Conteúdo de uma entrega (links, peças, calendário ou texto) — usado na revisão e na tela de aprovado.
// Tudo sai do conteúdo real da entrega; o que não veio é dito com um estado vazio, nunca com exemplo.
import type { EntregaGerada } from '../../state/projetos';
import { eventosDaEntrega, linksDaEntrega, rotuloDoLink, textosDaEntrega } from '../ui/conteudoDaEntrega';
import { ImagensEntrega } from '../ui/ImagensEntrega';
import { imagensDaEntrega } from '../ui/imagensDaEntrega';

export function DeliveryContent({ entrega }: { entrega?: EntregaGerada; color?: string }) {
  if (!entrega) return <div className="review-empty">Entrega não disponível nesta versão.</div>;

  const heading = <div className="review-delivery__heading"><h4>{entrega.titulo}</h4><span>{entrega.resumo}</span></div>;
  if (entrega.tipo === 'links') {
    const links = linksDaEntrega(entrega);
    return <>{heading}<div className="review-links">{links.map((link) => {
      const r = rotuloDoLink(link);
      return <a key={link.url} href={link.url} target="_blank" rel="noreferrer" title={link.url}><span>{r.principal}</span><small>↗ {r.secundario || link.dominio}</small></a>;
    })}{!links.length && <div className="review-empty">Esta entrega não trouxe links.</div>}</div></>;
  }

  if (entrega.tipo === 'imagem') {
    // só imagens reais (anexo ou URL de imagem); sem nenhuma, diz isso em vez de inventar peças
    return <>{heading}{imagensDaEntrega(entrega).length
      ? <ImagensEntrega entrega={entrega} className="review-images" />
      : <div className="review-empty">Esta entrega não trouxe imagem.</div>}</>;
  }

  if (entrega.tipo === 'calendario') {
    const eventos = eventosDaEntrega(entrega);
    return <>{heading}<div className="review-calendar">{eventos.map((ev, index) => (
      <div className="review-calendar__item" key={`${ev.quando}-${index}`}><b>{ev.quando}</b> {ev.titulo}</div>
    ))}{!eventos.length && <div className="review-empty">Esta entrega não trouxe datas.</div>}</div></>;
  }

  const items = textosDaEntrega(entrega);
  if (!items.length) return <>{heading}<div className="review-empty">{entrega.tipo === 'texto' ? 'Esta entrega não trouxe texto.' : 'Nada para mostrar nesta entrega.'}</div></>;
  return <>{heading}{items.length > 1
    ? <ul className="review-items">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    : <p className="review-text">{items[0]}</p>}</>;
}

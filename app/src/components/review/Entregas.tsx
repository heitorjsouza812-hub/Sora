// Conteúdo de uma entrega (links, peças, calendário ou texto) — usado na revisão e na tela de aprovado.
import type { EntregaGerada } from '../../state/projetos';
import { ImagensEntrega } from '../ui/ImagensEntrega';
import { imagensDaEntrega } from '../ui/imagensDaEntrega';

export function DeliveryContent({ entrega }: { entrega?: EntregaGerada; color?: string }) {
  if (!entrega) return <div className="review-empty">Entrega não disponível nesta versão.</div>;

  const heading = <div className="review-delivery__heading"><h4>{entrega.titulo}</h4><span>{entrega.resumo}</span></div>;
  if (entrega.tipo === 'links') {
    return <>{heading}<div className="review-links">{entrega.links?.map((link) => {
      const href = /^https?:\/\//.test(link.dominio) ? link.dominio : `https://${link.dominio}`;
      return <a key={`${link.dominio}-${link.titulo}`} href={href} target="_blank" rel="noreferrer"><span>{link.titulo}</span><small>↗ {link.dominio}</small></a>;
    })}{!entrega.links?.length && <div className="review-empty">Nenhum link nesta entrega.</div>}</div></>;
  }

  if (entrega.tipo === 'imagem') {
    // só imagens reais (anexo ou URL de imagem); sem nenhuma, diz isso em vez de inventar peças
    return <>{heading}{imagensDaEntrega(entrega).length
      ? <ImagensEntrega entrega={entrega} className="review-images" />
      : <div className="review-empty">Esta entrega não trouxe imagem.</div>}</>;
  }

  if (entrega.tipo === 'calendario') {
    const items = entrega.itens ?? [];
    return <>{heading}<div className="review-calendar">{items.map((item, index) => <div className="review-calendar__item" key={`${item}-${index}`}>{item}</div>)}{!items.length && <p className="review-text">{entrega.resumo}</p>}</div></>;
  }

  const items = entrega.itens ?? [];
  return <>{heading}{items.length > 1
    ? <ul className="review-items">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    : <p className="review-text">{items[0] ?? entrega.resumo}</p>}</>;
}

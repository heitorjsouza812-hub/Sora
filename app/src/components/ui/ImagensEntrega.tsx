// Imagens reais de uma entrega (captura do navegador, peça gerada). Sem imagem, não desenha nada:
// nada de miniatura inventada (regra "sem simulação").
import type { EntregaGerada } from '../../state/projetos';
import { ImagemAnexo } from './ImagemAnexo';
import { imagensDaEntrega } from './imagensDaEntrega';

export function ImagensEntrega({ entrega, className = 'delivery-images', limite, compacta = false }: {
  entrega: Pick<EntregaGerada, 'imagens' | 'conteudo' | 'titulo'>; className?: string; limite?: number; compacta?: boolean;
}) {
  const imagens = imagensDaEntrega(entrega).slice(0, limite);
  if (!imagens.length) return null;
  return (
    <div className={className}>
      {imagens.map((img, i) => {
        const alt = img.titulo ? `Imagem da entrega: ${img.titulo}` : `Imagem ${i + 1} da entrega ${entrega.titulo}`;
        return (
          <figure className="delivery-image" key={img.anexoId ?? img.src}>
            {img.anexoId
              ? <ImagemAnexo anexoId={img.anexoId} alt={alt} />
              : <img src={img.src} alt={alt} loading="lazy" referrerPolicy="no-referrer" />}
            {!compacta && (img.titulo || img.url) && (
              <figcaption>
                {img.titulo && <b>{img.titulo}</b>}
                {img.url && <a href={img.url} target="_blank" rel="noreferrer" title={img.url}>{img.url}</a>}
              </figcaption>
            )}
          </figure>
        );
      })}
    </div>
  );
}

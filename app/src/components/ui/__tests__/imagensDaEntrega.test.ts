import { describe, expect, it } from 'vitest';
import { imagensDaEntrega } from '../imagensDaEntrega';

const ID = '7f1c2a9e-4b2d-4c1e-9a7b-1f2e3d4c5b6a';

describe('imagensDaEntrega', () => {
  it('acha a captura do navegador sem usar /v1/anexos como página', () => {
    const conteudo = { dados: { capturas: [{ anexo_id: ID, nome: 'captura.png', url: `/v1/anexos/${ID}` }] } };
    expect(imagensDaEntrega({ conteudo })).toEqual([{ anexoId: ID, titulo: 'captura.png' }]);
  });

  it('a captura herda título e página do objeto de fora', () => {
    const conteudo = { dados: { titulo: 'IANA', url: 'https://www.iana.org/domains', captura: { anexo_id: ID, nome: 'captura.png' } } };
    expect(imagensDaEntrega({ conteudo })).toEqual([{ anexoId: ID, titulo: 'IANA', url: 'https://www.iana.org/domains' }]);
  });

  it('aceita anexo em texto, URL de imagem e legenda de página; tira repetidas', () => {
    const conteudo = { dados: [`/v1/anexos/${ID}`, `veja /v1/anexos/${ID}`, { imagem: 'https://cdn.x.com/a.png', titulo: 'Post', url: 'https://x.com/post' }] };
    expect(imagensDaEntrega({ conteudo })).toEqual([{ anexoId: ID }, { src: 'https://cdn.x.com/a.png', titulo: 'Post', url: 'https://x.com/post' }]);
  });

  it('nada de imagem: lista vazia (páginas, texto e javascript: não viram imagem)', () => {
    const conteudo = { dados: { url: 'https://www.iana.org/domains', titulo: 'IANA', texto: 'Abrimos!', img: 'javascript:alert(1)' } };
    expect(imagensDaEntrega({ conteudo })).toEqual([]);
    expect(imagensDaEntrega({})).toEqual([]);
  });
});

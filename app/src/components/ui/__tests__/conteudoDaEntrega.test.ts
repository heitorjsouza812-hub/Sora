import { describe, expect, it } from 'vitest';
import { MODELOS_AGENTE } from '../../projetos/modelos';
import { FERRAMENTAS_AGENTE, ferramentasParaSalvar } from '../../../data/ferramentas';
import { eventosDaEntrega, linksDaEntrega, rotuloDoLink, textosDaEntrega } from '../conteudoDaEntrega';

const envelope = (dados: unknown, fontes: unknown[] = []) => ({ conteudo: { dados, fontes, pendencias: [] } });

describe('conteudoDaEntrega', () => {
  it('links: objetos, textos e fontes; só http(s); sem anexo; sem repetir', () => {
    const e = envelope({ referencias: [{ title: 'A', link: 'https://www.a.com/x' }, 'https://b.com', 'javascript:alert(1)', '/v1/anexos/abc'] }, ['https://b.com', 'ftp://c.com']);
    expect(linksDaEntrega(e)).toEqual([
      { titulo: 'A', url: 'https://www.a.com/x', dominio: 'a.com' },
      { titulo: 'b.com', url: 'https://b.com/', dominio: 'b.com' },
    ]);
    expect(linksDaEntrega(envelope('texto sem link'))).toEqual([]);
  });

  it('texto: string em parágrafos, lista ou { texto }', () => {
    expect(textosDaEntrega(envelope('Um.\n\nDois.'))).toEqual(['Um.', 'Dois.']);
    expect(textosDaEntrega(envelope(['a', { texto: 'b' }]))).toEqual(['a', 'b']);
    expect(textosDaEntrega(envelope({ corpo: 'c' }))).toEqual(['c']);
    expect(textosDaEntrega(envelope({ x: 1 }))).toEqual([]);
  });

  it('calendário: só itens com data e assunto', () => {
    expect(eventosDaEntrega(envelope({ posts: [{ data: '2026-11-10', tema: 'Abertura' }, { tema: 'sem data' }, { dia: 3, legenda: 'Bastidores' }] }))).toEqual([
      { quando: '2026-11-10', titulo: 'Abertura' }, { quando: 'Dia 3', titulo: 'Bastidores' },
    ]);
    expect(eventosDaEntrega(envelope('nada'))).toEqual([]);
  });
});

describe('ferramentas do agente', () => {
  const catalogo = new Set(FERRAMENTAS_AGENTE.map(f => f.id));

  it('salva as escolhidas do catálogo + falar/perguntar; vazio deixa o padrão do backend', () => {
    expect(ferramentasParaSalvar(['buscar_web', 'Perplexity', 'buscar_web'])).toEqual(['falar', 'perguntar', 'buscar_web']);
    expect(ferramentasParaSalvar(['Perplexity'])).toEqual([]);
  });

  it('modelos de agente só usam ferramentas que o backend aceita', () => {
    for (const m of MODELOS_AGENTE) for (const f of m.rascunho.ferramentas) expect(catalogo.has(f), `${m.id}: ${f}`).toBe(true);
  });
});

describe('rótulo do link (celular: "Referênci…" não distinguia dois links)', () => {
  const link = (titulo: string, url: string) => ({ titulo, url, dominio: new URL(url).hostname.replace(/^www\./, '') });

  it('título genérico ou longo: domínio/caminho em cima, título embaixo', () => {
    expect(rotuloDoLink(link('Referência de exemplo A', 'https://example.com/a'))).toEqual({ principal: 'example.com/a', secundario: 'Referência de exemplo A' });
    expect(rotuloDoLink(link('x'.repeat(60), 'https://www.loja.com/produtos/cafe/?utm=1'))).toEqual({ principal: 'loja.com/produtos/cafe', secundario: 'x'.repeat(60) });
  });

  it('título bom fica em cima; sem título, só o caminho', () => {
    expect(rotuloDoLink(link('Guia de cafés especiais', 'https://cafe.org/guia'))).toEqual({ principal: 'Guia de cafés especiais', secundario: 'cafe.org/guia' });
    expect(rotuloDoLink(link('b.com', 'https://b.com/'))).toEqual({ principal: 'b.com', secundario: '' });
  });
});

describe('caminho longo', () => {
  it('mostra o domínio e o último trecho, que é o que costuma diferir', () => {
    expect(rotuloDoLink({ titulo: 'Referência', url: 'https://www.loja.com.br/categorias/bebidas/cafes/especial-da-casa', dominio: 'loja.com.br' }).principal)
      .toBe('loja.com.br/…/especial-da-casa');
  });
});

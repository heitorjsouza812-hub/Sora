import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ResultadoResumo } from '../ChamadaFerramenta';

afterEach(cleanup);
describe('links do painel Trabalho', () => {
  it('título vira link só para http/https; sem url continua texto', () => {
    render(<ResultadoResumo resultado={{ resumo: '3 resultados', itens: [], links: [
      { titulo: 'Guia', dominio: 'example.com', url: 'https://example.com/guia' },
      { titulo: 'Perigo', dominio: 'x.com', url: 'javascript:alert(1)' },
      { titulo: 'Sem url', dominio: 'y.com' },
    ] }} />);
    const guia = screen.getByRole('link', { name: 'Guia' });
    expect(guia.getAttribute('href')).toBe('https://example.com/guia'); expect(guia.getAttribute('target')).toBe('_blank'); expect(guia.getAttribute('rel')).toContain('noopener');
    expect(screen.queryByRole('link', { name: 'Perigo' })).toBeNull(); expect(screen.queryByRole('link', { name: 'Sem url' })).toBeNull();
    expect(screen.getByText('Sem url')).toBeTruthy();
  });
});

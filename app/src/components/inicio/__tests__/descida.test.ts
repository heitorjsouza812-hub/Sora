import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { animarDescida, fantasma, DUR_DESCIDA } from '../descida';

const animar = vi.fn(() => ({ finished: Promise.resolve() }));
let reduzido = false;

beforeEach(() => {
  animar.mockClear(); reduzido = false;
  (HTMLElement.prototype as unknown as { animate: unknown }).animate = animar;
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: reduzido && q.includes('prefers-reduced-motion'), media: q, addEventListener: () => {}, removeEventListener: () => {} }));
  document.body.innerHTML = '';
});
afterEach(() => { delete (HTMLElement.prototype as unknown as { animate?: unknown }).animate; });

const caixa = (top: number, height = 50): DOMRect => ({ top, left: 100, width: 700, height, bottom: top + height, right: 800, x: 100, y: top, toJSON: () => ({}) });
const elemento = (top: number) => {
  const el = document.createElement('div');
  el.getBoundingClientRect = () => caixa(top);
  document.body.append(el);
  return el;
};

describe('descida do compositor (FLIP)', () => {
  it('anima só transform, do lugar antigo para o novo, em 420 ms', () => {
    const el = elemento(800);
    animarDescida(el, caixa(430));
    expect(animar).toHaveBeenCalledTimes(1);
    const [quadros, opcoes] = animar.mock.calls[0] as unknown as [Record<string, string>[], { duration: number }];
    expect(quadros[0]).toEqual({ transform: 'translate(0px, -370px)' });
    expect(quadros[1]).toEqual({ transform: 'none' });
    expect(opcoes.duration).toBe(DUR_DESCIDA);
    expect(JSON.stringify(quadros)).not.toMatch(/"(top|margin)/);
  });

  it('com movimento reduzido a troca é direta', () => {
    reduzido = true;
    animarDescida(elemento(800), caixa(430));
    expect(animar).not.toHaveBeenCalled();
  });

  it('não anima se o elemento não saiu do lugar', () => {
    animarDescida(elemento(430), caixa(430));
    expect(animar).not.toHaveBeenCalled();
  });

  it('o que sai de cena fica como cópia fixa e é apagado depois do fade', async () => {
    const el = elemento(300);
    el.innerHTML = '<h1>Em que posso te ajudar hoje?</h1>';
    fantasma(el);
    const copia = document.body.lastElementChild as HTMLElement;
    expect(copia).not.toBe(el);
    expect(copia.style.position).toBe('fixed');
    expect(copia.textContent).toContain('Em que posso');
    await Promise.resolve(); await Promise.resolve();
    expect(document.body.contains(copia)).toBe(false);
  });
});

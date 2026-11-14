import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('../markdownSeguro', async original => {
 const atual = await original<typeof import('../markdownSeguro')>(); return { markdownSeguro: vi.fn(atual.markdownSeguro) };
});
import { Markdown } from '../Markdown';
import { markdownSeguro } from '../markdownSeguro';
import { useRolagemFim } from '../useRolagemFim';
import { IrParaFim } from '../IrParaFim';
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('streaming e markdown', () => {
 it('5.000 caracteres em 100 atualizações fazem no máximo um parse por quadro', () => {
  const quadros: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => { quadros.push(f); return quadros.length; });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const parse = vi.mocked(markdownSeguro); parse.mockClear();
  const view = render(<Markdown texto="" gerando />);
  expect(parse).toHaveBeenCalledTimes(1);
  for (let i=1; i<=100; i++) view.rerender(<Markdown texto={'a'.repeat(i*50)} gerando />);
  expect(quadros).toHaveLength(1); expect(parse).toHaveBeenCalledTimes(1);
  act(() => quadros.shift()!(16));
  expect(parse).toHaveBeenCalledTimes(2); expect(view.container.textContent?.trim()).toBe('a'.repeat(5000));
  view.rerender(<Markdown texto={'a'.repeat(5000)+' fim'} />);
  act(() => quadros.shift()!(32));
  expect(parse).toHaveBeenCalledTimes(3); expect(view.container.textContent).toContain(' fim');
 });
 it('carrega realce por classes e mantém código hostil como texto', async () => {
  const { container } = render(<Markdown texto={'```python\ndef exemplo():\n    return "<img src=x onerror=alert(1)>"\n```'} />);
  await vi.waitFor(() => expect(container.querySelector('.hljs-keyword')).not.toBeNull());
  expect(container.querySelector('[style], img, script')).toBeNull();
  expect(container.querySelector('code')?.textContent).toContain('<img src=x onerror=alert(1)>');
 });
 it('não força scroll durante leitura e permite voltar ao fim', () => {
  function Chat({ texto }: { texto: string }) {
   const { ref, onScroll, noFim, novas, irParaFim } = useRolagemFim(['m1'], texto);
   return <><div data-testid="scroll" ref={ref} onScroll={onScroll}><p data-chave="m1">{texto}</p></div>{!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}</>;
  }
  const view=render(<Chat texto="início" />); const el=screen.getByTestId('scroll');
  Object.defineProperties(el,{ scrollHeight: { configurable: true, value: 1000 }, clientHeight: { value: 200 } });
  el.scrollTop=200; fireEvent.scroll(el);
  Object.defineProperty(el,'scrollHeight',{value:1500}); view.rerender(<Chat texto="resposta mais longa" />);
  expect(el.scrollTop).toBe(200); expect(screen.getByRole('button',{name:'Ir para o fim'})).toBeTruthy();
  vi.stubGlobal('matchMedia',()=>({ matches:true })); el.scrollTo=vi.fn();
  fireEvent.click(screen.getByRole('button',{name:'Ir para o fim'})); expect(el.scrollTo).toHaveBeenCalledWith({ top:1500, behavior:'auto' });
 });
});

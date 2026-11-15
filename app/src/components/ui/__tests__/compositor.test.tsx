import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ctl = vi.hoisted(() => ({ celular: false, beam: [] as Array<{ active?: boolean; strength?: number }> }));
vi.mock('border-beam', () => ({ BorderBeam: ({ children, active, strength }: { children: ReactNode; active?: boolean; strength?: number }) => { ctl.beam.push({ active, strength }); return <div>{children}</div>; } }));
vi.mock('voice-glow', () => ({
  VoiceBeam: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }),
}));

import { MessageComposer } from '../MessageComposer';

const consulta = (q: string) => ({ matches: q.includes('max-width: 767px') ? ctl.celular : false, media: q, addEventListener: () => {}, removeEventListener: () => {} });
beforeEach(() => { ctl.celular = false; ctl.beam = []; vi.stubGlobal('matchMedia', consulta); });

describe('compositor único (etapa 6)', () => {
  it('o "+" de anexar aparece também no compacto, antes do campo, e Enviar começa desativado', () => {
    const { container } = render(<MessageComposer placeholder="Mensagem para a Sora…" onSend={() => {}} />);
    const form = container.querySelector('form.composer') as HTMLElement;
    expect(form).toHaveClass('composer-compact');
    const esq = form.querySelector('.composer-esq') as HTMLElement;
    expect(within(esq).getByRole('button', { name: 'Anexar arquivos' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar mensagem' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Mensagem para a Sora…'), { target: { value: 'oi' } });
    expect(screen.getByRole('button', { name: 'Enviar mensagem' })).toBeEnabled();
  });

  it('o estado grande tem texto em cima e ações embaixo', () => {
    const { container } = render(<MessageComposer placeholder="Mensagem para a Sora…" grande />);
    expect(container.querySelector('form.composer')).toHaveClass('composer-grande');
  });

  it('botões extras (voz, @) ficam dentro do campo, à direita', () => {
    const { container } = render(<MessageComposer placeholder="Mensagem" voz acoesDireita={<button type="button" aria-label="Conversar por voz">v</button>} />);
    const dir = container.querySelector('.composer-dir') as HTMLElement;
    expect(within(dir).getByRole('button', { name: 'Conversar por voz' })).toBeInTheDocument();
    expect(within(dir).getByRole('button', { name: 'Ativar microfone' })).toBeInTheDocument();
    expect(container.querySelector('form.composer > .conversa-voz')).toBeNull();
  });

  it('no celular o placeholder é curto quando o nome não cabe, e o rótulo acessível segue completo', () => {
    ctl.celular = true;
    render(<MessageComposer placeholder="Mensagem para Bot de pesquisa…" />);
    const campo = screen.getByLabelText('Mensagem para Bot de pesquisa…');
    expect(campo).toHaveAttribute('placeholder', 'Mensagem…');
  });

  it('o beam só aparece com foco e fica mais forte ao digitar', () => {
    render(<MessageComposer placeholder="Mensagem" />);
    expect(ctl.beam.at(-1)).toMatchObject({ active: false });
    const campo = screen.getByLabelText('Mensagem');
    fireEvent.focus(campo);
    expect(ctl.beam.at(-1)).toMatchObject({ active: true, strength: 0.45 });
    fireEvent.change(campo, { target: { value: 'a' } });
    expect(ctl.beam.at(-1)).toMatchObject({ active: true, strength: 0.7 });
    fireEvent.blur(campo);
    expect(ctl.beam.at(-1)?.active).toBe(false);
  });

  it('com movimento reduzido não há beam (a borda de foco é do CSS)', () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('prefers-reduced-motion') || q.includes('max-width: 767px') ? q.includes('prefers-reduced-motion') : false, media: q, addEventListener: () => {}, removeEventListener: () => {} }));
    render(<MessageComposer placeholder="Mensagem" />);
    fireEvent.focus(screen.getByLabelText('Mensagem'));
    expect(ctl.beam.at(-1)?.active).toBe(false);
  });
});

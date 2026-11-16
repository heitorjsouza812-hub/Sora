import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AUTOMATICO, type PreferenciasConversa } from '../../../api/preferenciasConversa';

const ctl = vi.hoisted(() => ({ celular: false, parou: 0 }));
vi.mock('../useMedia', () => ({ useCelular: () => ctl.celular, useMedia: () => false }));
vi.mock('border-beam', () => ({ BorderBeam: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('voice-glow', () => ({
  VoiceBeam: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }),
}));
const m = (id: string, modelo: string, p: string, extra = {}) => ({ id, modelo, provedor_id: p, ativo: true, capacidades: ['ferramentas'], ...extra });
vi.mock('../../../state/modelos', async importar => {
  const original = await importar<typeof import('../../../state/modelos')>();
  return {
    ...original,
    useModelos: () => ({
      carregando: false, erro: null,
      provedores: { gemini: { conexao: { id: 'pg', tipo: 'google' } }, groq: { conexao: { id: 'pq', tipo: 'groq' } } },
      modelos: [
        m('1', 'gemini-2.5-flash', 'pg', { raciocinio: ['baixo', 'medio', 'alto'] }),
        m('2', 'gemini-2.5-pro', 'pg', { raciocinio: ['baixo', 'alto'] }),
        m('3', 'gemini-1.0-pro', 'pg'),
        m('4', 'gemini-1.5-flash-8b', 'pg'),
        m('5', 'openai/gpt-oss-120b', 'pq', { raciocinio: ['baixo', 'medio', 'alto'] }),
      ],
    }),
  };
});

import { MessageComposer } from '../MessageComposer';

function Campo({ gerando = false, valorInicial = AUTOMATICO }: { gerando?: boolean; valorInicial?: PreferenciasConversa }) {
  const [valor, mudar] = useState(valorInicial);
  return <MessageComposer placeholder="Mensagem" voz onSend={() => {}} gerando={gerando} onParar={() => { ctl.parou += 1; }} preferencias={{ valor, mudar }} />;
}
beforeEach(() => {
  ctl.celular = false; ctl.parou = 0;
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} }));
});

describe('botão do modelo no compositor', () => {
  it('fica à direita, antes do microfone e do enviar', () => {
    const { container } = render(<Campo />);
    const dir = container.querySelector('.composer-dir') as HTMLElement;
    const nomes = within(dir).getAllByRole('button').map(b => b.getAttribute('aria-label') ?? b.textContent);
    expect(nomes[0]).toMatch(/Automático/);
    expect(nomes.slice(1)).toEqual(['Ativar microfone', 'Enviar mensagem']);
    expect(container.querySelector('.composer-esq .seletor-gatilho')).toBeNull();
  });

  it('Automático usa o ícone de brilho e não mostra nível', () => {
    const { container } = render(<Campo />);
    expect(container.querySelector('.seletor-gatilho svg')?.getAttribute('data-provedor')).toBe('auto');
    expect(container.querySelector('.seletor-nivel')).toBeNull();
  });

  it('mostra ícone do provedor, nome limpo e nível mais apagado ao lado', () => {
    const { container } = render(<Campo valorInicial={{ ...AUTOMATICO, provedor_id: 'pq', modelo: 'openai/gpt-oss-120b', raciocinio: 'alto' }} />);
    const gatilho = container.querySelector('.seletor-gatilho') as HTMLElement;
    expect(gatilho.querySelector('svg')?.getAttribute('data-provedor')).toBe('groq');
    expect(gatilho.querySelector('.seletor-nome')).toHaveTextContent('GPT-OSS 120B');
    expect(gatilho.querySelector('.seletor-nivel')).toHaveTextContent('Alto');
  });

  it('raciocínio automático ou modelo sem nível deixa o nível vazio', () => {
    const a = render(<Campo valorInicial={{ ...AUTOMATICO, provedor_id: 'pg', modelo: 'gemini-2.5-flash', raciocinio: 'auto' }} />);
    expect(a.container.querySelector('.seletor-nivel')).toBeNull();
    a.unmount();
    const b = render(<Campo valorInicial={{ ...AUTOMATICO, provedor_id: 'pg', modelo: 'gemini-1.0-pro', raciocinio: 'alto' }} />);
    expect(b.container.querySelector('.seletor-nivel')).toBeNull();
  });

  it('no celular o nome continua no botão só para leitores de tela e o nível aparece', () => {
    ctl.celular = true;
    const { container } = render(<Campo valorInicial={{ ...AUTOMATICO, provedor_id: 'pg', modelo: 'gemini-2.5-pro', raciocinio: 'medio' }} />);
    expect(container.querySelector('.seletor-gatilho')).toHaveTextContent('Gemini 2.5 Pro');
    expect(container.querySelector('.seletor-nivel')).toHaveTextContent('Médio');
  });

  it('lista os principais e deixa o resto atrás de "Mais modelos"', () => {
    render(<Campo />);
    fireEvent.click(screen.getByRole('button', { name: /Automático/ }));
    expect(screen.getByRole('button', { name: /Gemini 2.5 Pro/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Gemini 1.0 Pro/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mais modelos (2)' }));
    expect(screen.getByRole('button', { name: /Gemini 1.0 Pro/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Gemini 1.5 Flash 8B/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Só os principais' }));
    expect(screen.queryByRole('button', { name: /Gemini 1.0 Pro/ })).not.toBeInTheDocument();
  });

  it('a busca encontra também os modelos que estão atrás de "Mais modelos"', () => {
    render(<Campo />);
    fireEvent.click(screen.getByRole('button', { name: /Automático/ }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Buscar modelos' }), { target: { value: '1.0' } });
    expect(screen.getByRole('button', { name: /Gemini 1.0 Pro/ })).toBeInTheDocument();
  });
});

describe('Enviar vira Parar enquanto trabalha', () => {
  it('quadrado de Parar chama onParar e volta a ser a seta quando termina', () => {
    const { rerender } = render(<Campo gerando />);
    const parar = screen.getByRole('button', { name: 'Parar resposta' });
    expect(parar).toHaveClass('is-parar');
    fireEvent.click(parar);
    expect(ctl.parou).toBe(1);
    expect(screen.queryByRole('button', { name: 'Enviar mensagem' })).not.toBeInTheDocument();
    rerender(<Campo gerando={false} />);
    expect(screen.getByRole('button', { name: 'Enviar mensagem' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Parar resposta' })).not.toBeInTheDocument();
  });
});

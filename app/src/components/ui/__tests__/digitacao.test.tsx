import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

// BorderBeam e VoiceBeam rodam um efeito que depende de `children` e grava estado novo a cada execução.
// Se `children` mudar a cada tecla, digitar rápido estoura o limite de atualizações do React e engole letras
// (achado no Chrome: "exampl.com", "psquisador"). O campo tem de repassar SEMPRE o mesmo elemento.
const filhos = vi.hoisted(() => ({ beam: [] as unknown[], voz: [] as unknown[] }));
vi.mock('border-beam', () => ({ BorderBeam: ({ children }: { children: ReactNode }) => { filhos.beam.push(children); return <div>{children}</div>; } }));
vi.mock('voice-glow', () => ({
  VoiceBeam: ({ children }: { children: ReactNode }) => { filhos.voz.push(children); return <div>{children}</div>; },
  useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }),
}));

import { MessageComposer } from '../MessageComposer';

vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} }));

describe('campo de mensagem: digitação', () => {
  it('o BorderBeam e o VoiceBeam recebem o mesmo `children` a cada tecla, e o texto não perde letras', () => {
    render(<MessageComposer placeholder="Peça qualquer coisa" />);
    const campo = screen.getByLabelText('Peça qualquer coisa') as HTMLTextAreaElement;
    let texto = '';
    for (const letra of 'o domínio example.com, citando') {
      texto += letra;
      fireEvent.change(campo, { target: { value: texto } });
    }
    expect(campo.value).toBe(texto);
    expect(filhos.beam.length).toBeGreaterThan(5);
    expect(new Set(filhos.beam).size).toBe(1);
    expect(new Set(filhos.voz).size).toBe(1);
  });
});

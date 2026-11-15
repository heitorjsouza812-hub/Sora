import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('border-beam', () => ({ BorderBeam: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('voice-glow', () => ({
  VoiceBeam: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }),
}));
vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} }));
// O orb de verdade é um canvas: aqui ele só registra a cor e o movimento que recebeu.
vi.mock('../../mascot', () => ({ SoraOrb: ({ color, movimento }: { color?: string; movimento?: string }) => <span data-testid="orb" data-cor={color} data-movimento={movimento} /> }));

const enviarAnexo = vi.hoisted(() => vi.fn());
vi.mock('../../../api/anexos', () => ({ enviarAnexo }));
const enviarNaRota = vi.hoisted(() => vi.fn());
vi.mock('../../../api/grupos', async (importar) => {
  const original = await importar<typeof import('../../../api/grupos')>();
  return { ...original, enviarMensagemGrupo: enviarNaRota };
});

import { _definirBotsParaTestes, _reiniciarBotsParaTestes } from '../../../state/bots';
import { _reiniciarGruposParaTestes, lerGrupos } from '../../../state/grupos';
import type { BotResumo } from '../../../state/bots';
import type { MensagemGrupoApi } from '../../../api/grupos';
import { CompositorGrupo } from '../CompositorGrupo';
import { MensagemGrupo } from '../MensagemGrupo';
import { completarMencao, opcoesDeMencao } from '../mencoes';

const SORA = 'sora-1';
const bot = (id: string, nome: string, cor: string, movimento: 'gira' | 'espiral' = 'gira') => ({ id, tipo: 'individual' as const, nome, funcao: 'Função', cor, movimento, ferramentas: [], estado: 'livre' as const });
const mensagem = (parcial: Partial<MensagemGrupoApi>): MensagemGrupoApi => ({ id: 'm1', grupoId: 'g1', sequencia: 1, autor: 'bot', botId: null, texto: '', tipo: 'mensagem', respondeA: null, anexos: [], criadaEm: '', ...parcial });

beforeEach(() => {
  _reiniciarGruposParaTestes(); _reiniciarBotsParaTestes();
  _definirBotsParaTestes([bot('b1', 'Atlas', '#56A8FF'), bot('b2', 'Luna', '#AC80FF', 'espiral')]);
  enviarAnexo.mockReset(); enviarNaRota.mockReset();
});

describe('mensagens do grupo', () => {
  it('bot e Sora respondem com markdown (tabela e código) e o orb na cor de quem fala', () => {
    const tabela = '| Canal | Alcance |\n| --- | --- |\n| Instagram | 12 mil |\n\n```ts\nconst total = 3;\n```';
    const { container } = render(<div>
      <MensagemGrupo mensagem={mensagem({ id: 'm1', botId: 'b2', texto: tabela })} todas={[]} soraId={SORA} onResponder={() => undefined} />
      <MensagemGrupo mensagem={mensagem({ id: 'm2', autor: 'agente' as 'bot', botId: SORA, texto: '**Pronto**' })} todas={[]} soraId={SORA} onResponder={() => undefined} />
    </div>);
    expect(container.querySelector('table')).not.toBeNull();
    expect(screen.getByText('Instagram')).toBeTruthy();
    expect(container.querySelector('.md-code code')?.textContent).toContain('const total = 3;');
    expect(container.querySelector('.md strong')?.textContent).toBe('Pronto');
    const orbs = screen.getAllByTestId('orb');
    expect(orbs.map(orb => orb.getAttribute('data-cor'))).toEqual(['#AC80FF', '#E2ECFF']);
    expect(orbs[0].getAttribute('data-movimento')).toBe('espiral');
    expect(screen.getByText('Luna')).toBeTruthy();
    expect(screen.getByText('Sora')).toBeTruthy();
  });

  it('a fala do usuário continua texto puro, sem orb', () => {
    render(<div><MensagemGrupo mensagem={mensagem({ autor: 'usuario', texto: '**não** é markdown' })} todas={[]} soraId={SORA} onResponder={() => undefined} /></div>);
    expect(screen.getByText('**não** é markdown')).toBeTruthy();
    expect(screen.queryByTestId('orb')).toBeNull();
  });
});

describe('menções', () => {
  const bots: Pick<BotResumo, 'id' | 'nome' | 'cor'>[] = [{ id: 'b1', nome: 'Átlas', cor: '#56A8FF' }, { id: 'b2', nome: 'Luna', cor: '#AC80FF' }];
  it('filtra sem acento pelo começo do nome e completa só o nome', () => {
    expect(opcoesDeMencao('oi @', bots).map(o => o.nome)).toEqual(['todos', 'Átlas', 'Luna']);
    expect(opcoesDeMencao('oi @at', bots).map(o => o.nome)).toEqual(['Átlas']);
    expect(opcoesDeMencao('oi a@b', bots)).toEqual([]);
    expect(completarMencao('oi @lu', 'Luna')).toBe('oi @Luna ');
    expect(completarMencao('@to', 'todos')).toBe('@todos ');
  });
});

describe('campo do grupo', () => {
  const montar = () => {
    const botsDoGrupo = [{ id: 'b1', nome: 'Atlas', cor: '#56A8FF', funcao: '', estado: 'livre' as const, ferramentas: [] }, { id: 'b2', nome: 'Luna', cor: '#AC80FF', funcao: '', estado: 'livre' as const, ferramentas: [] }];
    const retorno = render(<CompositorGrupo grupoId="g1" botsDoGrupo={botsDoGrupo} resposta={null} onCancelarResposta={() => undefined} onEnviado={() => undefined} />);
    const campo = screen.getByLabelText(/Mensagem para o grupo/) as HTMLTextAreaElement;
    return { ...retorno, campo };
  };

  it('Shift+Enter quebra a linha e Enter envia o texto inteiro', async () => {
    enviarNaRota.mockResolvedValue(mensagem({ id: 'novo', autor: 'usuario', texto: 'a\nb' }));
    const { campo } = montar();
    fireEvent.change(campo, { target: { value: 'linha 1\nlinha 2' } });
    fireEvent.keyDown(campo, { key: 'Enter', shiftKey: true });
    expect(enviarNaRota).not.toHaveBeenCalled();
    fireEvent.keyDown(campo, { key: 'Enter' });
    await waitFor(() => expect(enviarNaRota).toHaveBeenCalledTimes(1));
    expect(enviarNaRota.mock.calls[0][1]).toEqual(expect.objectContaining({ texto: 'linha 1\nlinha 2', anexos: [] }));
    await waitFor(() => expect(campo.value).toBe(''));
  });

  it('colar arquivo vira anexo, sobe antes da mensagem e vai pelos ids', async () => {
    enviarAnexo.mockResolvedValue({ anexo_id: 'a1', nome: 'notas.txt', tipo: 'text/plain', tamanho: 5 });
    enviarNaRota.mockResolvedValue(mensagem({ id: 'novo', autor: 'usuario', texto: 'veja' }));
    const { campo } = montar();
    const arquivo = new File(['ola'], 'notas.txt', { type: 'text/plain' });
    fireEvent.paste(campo, { clipboardData: { files: [arquivo], types: ['Files'] } });
    expect(await screen.findByText('notas.txt')).toBeTruthy();
    fireEvent.change(campo, { target: { value: 'veja' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    await waitFor(() => expect(enviarNaRota).toHaveBeenCalled());
    expect(enviarAnexo).toHaveBeenCalledWith(arquivo);
    expect(enviarNaRota.mock.calls[0][1]).toEqual(expect.objectContaining({ texto: 'veja', anexos: ['a1'] }));
  });

  it('o botão de anexar e o de microfone seguem o chat 1:1 (anexar sim, voz não)', () => {
    montar();
    expect(screen.getByRole('button', { name: 'Anexar arquivos' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Ativar microfone' })).toBeNull();
  });

  it('@ abre a lista; ↓ e Enter escolhem sem enviar; Esc fecha', async () => {
    const { campo } = montar();
    fireEvent.change(campo, { target: { value: 'oi @' } });
    const opcoes = screen.getAllByRole('option');
    expect(opcoes.map(o => o.textContent)).toEqual(['@todos', '@Atlas', '@Luna']);
    expect(opcoes[0].getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(campo, { key: 'ArrowDown' });
    expect(screen.getAllByRole('option')[1].getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(campo, { key: 'ArrowUp' });
    fireEvent.keyDown(campo, { key: 'ArrowUp' });
    expect(screen.getAllByRole('option')[2].getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(campo, { key: 'Enter' });
    expect(campo.value).toBe('oi @Luna ');
    expect(enviarNaRota).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).toBeNull();

    fireEvent.change(campo, { target: { value: 'oi @a' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
    fireEvent.keyDown(campo, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(campo.value).toBe('oi @a');
  });

  it('409 do servidor relê os grupos e devolve o texto ao campo', async () => {
    const { ErroApi } = await import('../../../api/cliente');
    enviarNaRota.mockRejectedValue(new ErroApi(409, 'Este grupo precisa de pelo menos 2 bots. Adicione bots para continuar.'));
    const { campo } = montar();
    fireEvent.change(campo, { target: { value: 'oi' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    expect((await screen.findByRole('alert')).textContent).toContain('pelo menos 2 bots');
    await waitFor(() => expect(campo.value).toBe('oi'));
    expect(lerGrupos()).toBeTruthy();
  });
});

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
const post = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());
const buscarAutenticado = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api: { post, get, put: vi.fn() }, buscarAutenticado }));

import { receberEventoEquipe, reiniciarEquipe } from '../../../state/equipe';
import { lerTelas, reiniciarTelas } from '../../../state/telas';
import { TelasDoBot } from '../TelasDoBot';

const aba = (assumida = false) => ({ aba_id: 'x', agente_id: 'a1', url: 'https://loja.com', titulo: 'Loja', carregada: true, assumida_pelo_usuario: assumida });
const quadro = (assumida = false) => receberEventoEquipe({ tipo: 'navegador.tela', dados: { aba_id: 'x', agente_id: 'a1', url: 'https://loja.com', titulo: 'Loja', largura: 1280, altura: 800, miniatura: 'data:image/jpeg;base64,AAA', mudou: true, assumida_pelo_usuario: assumida, aviso: null } });
const visivel = (v: 'visible' | 'hidden') => Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => v });
const chamadas = (parte: string) => post.mock.calls.filter(c => String(c[0]).includes(parte));
const ALT = 'Tela ao vivo do navegador: Loja';

beforeEach(() => {
  post.mockResolvedValue({ enviado: true, expira_em_segundos: 12 });
  get.mockResolvedValue([]);
  buscarAutenticado.mockRejectedValue(new Error('404'));
  visivel('visible');
});
afterEach(() => { cleanup(); vi.useRealTimers(); post.mockReset(); get.mockReset(); buscarAutenticado.mockReset(); reiniciarEquipe(); reiniciarTelas(); });

describe('navegador ao vivo', () => {
  it('limpa imagens ao sair da conta e ao fechar a aba', () => {
    quadro();
    receberEventoEquipe({ tipo: 'navegador.aba', dados: { aba_id: 'x', fechada: true } });
    expect(lerTelas().navegador.a1).toBeUndefined();
    quadro(); reiniciarEquipe();
    expect(lerTelas().navegador).toEqual({});
  });

  it('trocar de bot encerra o assistir anterior', () => {
    vi.useFakeTimers(); quadro();
    const { rerender } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    rerender(<TelasDoBot agenteId="a2" usaComputador={false} />);
    act(() => vi.advanceTimersByTime(16000));
    expect(chamadas('/v1/agentes/a1/navegador/assistir')).toHaveLength(1);
  });

  it('devolver cancela texto e roda ainda pendentes; SSE atualiza o controle', async () => {
    vi.useFakeTimers(); quadro(true);
    const { container } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    const caixa = container.querySelector('.wk-tela-caixa')!;
    fireEvent.keyDown(caixa, { key: 'x' }); fireEvent.wheel(caixa, { deltaY: 50 });
    act(() => quadro(false));
    await act(async () => vi.advanceTimersByTime(500));
    expect(chamadas('/digitar')).toHaveLength(0);
    expect(chamadas('/rolar')).toHaveLength(0);
    expect(screen.queryByText('Você está no controle — o bot espera.')).toBeNull();
  });

  it('campo para teclado móvel envia sem manter o texto no DOM', async () => {
    quadro(true); render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    const campo = screen.getByLabelText('Digitar na aba') as HTMLInputElement;
    fireEvent.change(campo, { target: { value: 'teste' } });
    expect(campo.value).toBe('');
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/digitar', { texto: 'teste' }));
  });

  it('sem aba não mostra nada e não chama "assistir"', () => {
    const { container } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    expect(container.querySelector('.wk-tela')).toBeNull();
    expect(chamadas('assistir')).toHaveLength(0);
  });

  it('alterna as telas por teclado sem empilhar computador sob navegador', async () => {
    quadro();
    render(<TelasDoBot agenteId="a1" usaComputador />);
    expect(screen.getByAltText(ALT)).toBeTruthy();
    expect(screen.queryByText(/Ele liga sozinho/)).toBeNull();
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Navegador' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Computador' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByAltText(ALT)).toBeNull();
    expect(await screen.findByText(/Ele liga sozinho/)).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Navegador' }));
    expect(screen.getByAltText(ALT)).toBeTruthy();
  });

  it('mostra imagem, URL e tempo; chama "assistir" ao abrir e a cada 8 s; para com a página oculta e ao fechar o painel', () => {
    vi.useFakeTimers();
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba() }); quadro();
    const { unmount } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    expect(screen.getByAltText(ALT)).toBeTruthy();
    expect(screen.getByText('https://loja.com')).toBeTruthy();
    expect(screen.getByText(/atualizado/)).toBeTruthy();
    expect(chamadas('/v1/agentes/a1/navegador/assistir')).toHaveLength(1);
    act(() => { vi.advanceTimersByTime(8000); });
    expect(chamadas('assistir')).toHaveLength(2);
    visivel('hidden');
    act(() => { vi.advanceTimersByTime(16000); });
    expect(chamadas('assistir')).toHaveLength(2);
    unmount();
    visivel('visible');
    act(() => { vi.advanceTimersByTime(16000); });
    expect(chamadas('assistir')).toHaveLength(2);
  });

  it('sem imagem: estado vazio claro e Ampliar desativado', () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba() });
    render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    expect(screen.getByText(/Ainda não há imagem desta aba/)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Ampliar' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('assumida: moldura, aviso, clique na escala da imagem, teclas e rolagem; o texto digitado não aparece', async () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba(true) }); quadro(true);
    const rect = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ left: 10, top: 20, width: 640, height: 400, right: 650, bottom: 420, x: 10, y: 20, toJSON: () => ({}) });
    const { container } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    expect(screen.getByText('Você está no controle — o bot espera.')).toBeTruthy();
    expect(container.querySelector('.wk-tela.is-controle')).toBeTruthy();
    fireEvent.click(screen.getByAltText(ALT), { clientX: 110, clientY: 120 });
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/clicar', { x: 200, y: 200, largura: 1280, altura: 800 }));
    const caixa = container.querySelector('.wk-tela-caixa')!;
    fireEvent.keyDown(caixa, { key: 'o' }); fireEvent.keyDown(caixa, { key: 'i' });
    fireEvent.keyDown(caixa, { key: 'Enter' });
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/tecla', { tecla: 'Enter' }));
    const ordem = post.mock.calls.map(c => c[0]);
    expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/digitar', { texto: 'oi' });
    expect(ordem.indexOf('/v1/navegador/abas/x/digitar')).toBeLessThan(ordem.indexOf('/v1/navegador/abas/x/tecla'));
    fireEvent.wheel(caixa, { deltaY: 50 });
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/rolar', { dy: 100 }));
    expect(container.textContent).not.toContain('oi');
    rect.mockRestore();
  });

  it('não assumida: clique e teclas não mandam nada', () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba(false) }); quadro();
    const { container } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    fireEvent.click(screen.getByAltText(ALT));
    fireEvent.keyDown(container.querySelector('.wk-tela-caixa')!, { key: 'a' });
    expect(post.mock.calls.filter(c => /clicar|digitar|tecla/.test(String(c[0])))).toHaveLength(0);
  });

  it('assumir e devolver pelas rotas; depois de devolver avisa que o bot retoma na próxima ação', async () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba(false) }); quadro();
    post.mockImplementation(async (u: string) => u.endsWith('/assumir') ? aba(true) : u.endsWith('/devolver') ? aba(false) : { enviado: true });
    render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'Assumir a aba' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Devolver ao bot' }));
    expect(await screen.findByText(/bot retoma na próxima ação/)).toBeTruthy();
    expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/devolver');
  });

  it('ampliar abre o diálogo e busca o quadro inteiro', async () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: aba() }); quadro();
    URL.createObjectURL = vi.fn(() => 'blob:cheia'); URL.revokeObjectURL = vi.fn();
    buscarAutenticado.mockResolvedValue({ blob: async () => new Blob(['x']) });
    render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'Ampliar' }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    await waitFor(() => expect(buscarAutenticado).toHaveBeenCalledWith('/v1/navegador/abas/x/captura', expect.anything()));
  });
});

describe('computador do bot', () => {
  const pc = (extra: Record<string, unknown> = {}) => receberEventoEquipe({ tipo: 'computador.tela', dados: { agente_id: 'a1', alvo: 'virtual', ligado: true, geracao: 1, largura: 1280, altura: 800, miniatura: 'data:image/jpeg;base64,PPP', janela_ativa: 'Terminal', acao: 'Abriu o terminal', mudou: true, ...extra } });

  it('bot sem computador e sem quadro não mostra nada', () => {
    const { container } = render(<TelasDoBot agenteId="a1" usaComputador={false} />);
    expect(container.querySelector('.wk-tela')).toBeNull();
  });

  it('desligado: estado vazio, sem botão de desligar', async () => {
    get.mockResolvedValue({ agente_id: 'a1', disponivel: true, ligado: false, alvo: 'virtual', largura: null, altura: null, janela_ativa: null, acao: null, atualizado_em: null });
    render(<TelasDoBot agenteId="a1" usaComputador />);
    expect(await screen.findByText(/O computador do bot está desligado/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Desligar computador' })).toBeNull();
  });

  it('ligado: mostra a tela e a janela; desligar pede confirmação e usa a rota', async () => {
    get.mockResolvedValue({ agente_id: 'a1', disponivel: true, ligado: true, alvo: 'virtual', largura: 1280, altura: 800, janela_ativa: 'Terminal', acao: null, atualizado_em: null });
    pc();
    render(<TelasDoBot agenteId="a1" usaComputador />);
    expect(screen.getByAltText('Tela do computador do bot: Terminal')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Desligar computador' }));
    expect(post).not.toHaveBeenCalledWith('/v1/agentes/a1/computador/desligar');
    fireEvent.click(await screen.findByRole('button', { name: 'Desligar' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/agentes/a1/computador/desligar'));
    expect(await screen.findByText(/Desligamento solicitado/)).toBeTruthy();
    expect(screen.getByAltText('Tela do computador do bot: Terminal')).toBeTruthy();
    act(() => pc({ ligado: false, miniatura: null, geracao: 2 }));
    expect(await screen.findByText(/O computador do bot está desligado/)).toBeTruthy();
  });

  it('avisa quando a tela não mudou', () => {
    pc({ mudou: false });
    render(<TelasDoBot agenteId="a1" usaComputador />);
    expect(screen.getByText('A tela não mudou depois da última ação.')).toBeTruthy();
  });

  it('ligado sem imagem ainda: "Ligando"', () => {
    pc({ miniatura: null });
    render(<TelasDoBot agenteId="a1" usaComputador />);
    expect(screen.getByText('Ligando o computador do bot…')).toBeTruthy();
  });
});

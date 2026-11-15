import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const rede = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), buscar: vi.fn() }));
vi.mock('../../../api/cliente', async original => ({ ...await original<typeof import('../../../api/cliente')>(), api: rede, buscarAutenticado: rede.buscar }));
vi.mock('../../../api/eventos', () => ({ acompanharEventos: vi.fn(() => new Promise(() => {})) }));
import { _definirEstadoParaTestes, _reiniciarProjetosParaTestes, lerEstado, type MensagemChat as Mensagem } from '../../../state/projetos';
import { MensagemChat } from '../MensagemChat';

const pergunta: Mensagem = { id: 'p', conversaId: 'c', autor: 'usuario', texto: 'Oi @todos, resumam isto', criadoEm: 1 };
const resposta: Mensagem = { id: 'r', conversaId: 'c', autor: 'sora', texto: 'Resposta parcial', criadoEm: 2 };
function preparar(...ms: Mensagem[]) { _definirEstadoParaTestes({ ...lerEstado(), mensagens: ms }); }
afterEach(() => { cleanup(); _reiniciarProjetosParaTestes(); vi.clearAllMocks(); });

describe('mensagens (etapa 6)', () => {
  it('a pergunta é bolha à direita, com as ações na mesma linha, à esquerda, e menção destacada', () => {
    preparar(pergunta, resposta);
    const { container } = render(<MensagemChat m={pergunta} agora={0} />);
    const linha = container.querySelector('.user-linha') as HTMLElement;
    expect(linha.firstElementChild).toHaveClass('msg-acoes'); // ações antes da bolha: ficam à esquerda dela
    expect(linha.querySelector('.user-message')).toHaveTextContent('Oi @todos, resumam isto');
    expect(linha.querySelector('.user-message .mencao')).toHaveTextContent('@todos');
    expect(container.querySelector('.chat-msg.is-user .msg-barra')).toBeNull(); // não ocupa altura embaixo
  });

  it('a resposta tem cabeçalho de uma linha (avatar + nome) e texto sem coluna de avatar', () => {
    preparar(pergunta, resposta);
    const { container } = render(<MensagemChat m={resposta} agora={0} nome="Sora" avatar={<span data-testid="orb" />} rotulo="entregou" />);
    const cabeca = container.querySelector('.msg-cabeca') as HTMLElement;
    expect(within(cabeca).getByTestId('orb')).toBeInTheDocument();
    expect(cabeca).toHaveTextContent('Sora');
    expect(cabeca.querySelector('.msg-rotulo')).toHaveTextContent('entregou');
    expect(container.querySelector('.assistant-row')).toBeNull();
    expect(container.querySelector('.msg-corpo .md')).toHaveTextContent('Resposta parcial');
  });

  it('"Resposta interrompida" pertence à resposta, com Refazer resposta; nunca dentro da pergunta', () => {
    preparar(pergunta, { ...resposta, estado: 'interrompida' });
    const { container } = render(<><MensagemChat m={{ ...pergunta, estado: 'interrompida' }} agora={0} /><MensagemChat m={{ ...resposta, estado: 'interrompida' }} agora={0} nome="Sora" /></>);
    expect(container.querySelector('.chat-msg.is-user .msg-interrompida')).toBeNull();
    const aviso = container.querySelector('.chat-msg.is-assistant .msg-interrompida') as HTMLElement;
    expect(aviso).toHaveTextContent('Resposta interrompida');
    expect(within(aviso).getByRole('button', { name: 'Refazer resposta' })).toBeInTheDocument();
    expect(aviso).toHaveAttribute('role', 'status');
    expect(container.querySelector('.chat-msg.is-assistant .md')).toHaveTextContent('Resposta parcial'); // texto parcial continua
    expect(screen.getAllByRole('button', { name: 'Refazer resposta' })).toHaveLength(1); // a barra não repete o botão
  });

  it('parou antes do 1º caractere: o aviso ocupa o lugar da resposta, com o cabeçalho do autor', () => {
    const vazia = { ...resposta, texto: 'Resposta interrompida.', estado: 'interrompida' as const };
    preparar(pergunta, vazia);
    const { container } = render(<MensagemChat m={vazia} agora={0} nome="Sora" avatar={<span data-testid="orb" />} />);
    expect(container.querySelector('.msg-cabeca')).toHaveTextContent('Sora');
    expect(container.querySelector('.md')).toBeNull();
    expect(container.querySelector('.msg-interrompida')).toHaveTextContent('Resposta interrompida');
  });

  it('a última resposta marca as ações como sempre visíveis; a barra reserva o espaço desde o início', () => {
    preparar(pergunta, resposta);
    const { container, rerender } = render(<MensagemChat m={resposta} agora={0} ultima />);
    expect(container.querySelector('.chat-msg')).toHaveClass('is-ultima');
    expect(container.querySelector('.msg-barra')).not.toBeNull();
    rerender(<MensagemChat m={{ ...resposta, gerando: true }} agora={0} ultima />);
    expect(container.querySelector('.msg-barra')).not.toBeNull(); // gerando: vazia, mas o espaço continua reservado
    expect(container.querySelector('.msg-acoes')).toBeNull();
  });

  it('as ações formam um toolbar com ← → entre os botões e Copiar vira ✓ por 1,2 s', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    preparar(pergunta, resposta);
    const { container } = render(<MensagemChat m={resposta} agora={0} ultima />);
    const barra = screen.getByRole('toolbar', { name: 'Ações da mensagem' });
    const botoes = within(barra).getAllByRole('button');
    botoes[0].focus();
    fireEvent.keyDown(botoes[0], { key: 'ArrowRight' });
    expect(botoes[1]).toHaveFocus();
    fireEvent.keyDown(botoes[1], { key: 'ArrowLeft' });
    expect(botoes[0]).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Copiar' }));
    expect(container.querySelector('.msg-acao.is-ok')).not.toBeNull();
  });

  it('só a mensagem recém-criada anima; histórico não', () => {
    preparar(pergunta, resposta);
    const { container, unmount } = render(<MensagemChat m={{ ...pergunta, criadoEm: Date.now() }} agora={0} />);
    expect(container.querySelector('.chat-msg')).toHaveClass('is-nova');
    unmount();
    const velho = render(<MensagemChat m={pergunta} agora={0} />);
    expect(velho.container.querySelector('.chat-msg')).not.toHaveClass('is-nova');
  });
});

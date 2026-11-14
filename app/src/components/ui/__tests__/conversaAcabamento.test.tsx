import { act, fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
vi.mock('border-beam', () => ({ BorderBeam: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('voice-glow', () => ({ VoiceBeam: ({ children }: { children: ReactNode }) => <div>{children}</div>, useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }) }));
const mock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../../../api/cliente', async original => ({ ...await original<typeof import('../../../api/cliente')>(), api: { ...mock, patch: vi.fn(), delete: vi.fn() } }));
vi.mock('../../../api/eventos', () => ({ acompanharEventos: vi.fn(() => new Promise<void>(() => {})) }));
vi.mock('../../layout/Sidebar', () => ({ Sidebar: () => null, ContaRodape: () => null, Navegacao: () => null }));
vi.mock('../../builder', () => ({ EditorAgenteHost: () => null, MenuAgente: () => null }));
vi.mock('../../gestao', () => ({ GestaoHost: () => null }));
vi.mock('../../comandos', () => ({ Comandos: () => null }));
vi.mock('../../mascot', () => ({ SoraOrb: () => null }));
import { AppShell } from '../../layout/AppShell';
import { MensagemChat } from '../MensagemChat';
import { MessageComposer } from '../MessageComposer';
import { _reiniciarProjetosParaTestes, _definirEstadoParaTestes, lerEstado, enviarParaAgente, carregarMensagens, iniciarProjetos, useProjetos, tentarEnvioNovamente, _aplicarEventoParaTestes, conversarComSora } from '../../../state/projetos';

vi.stubGlobal('matchMedia', (media: string) => ({ matches: false, media, addEventListener: () => {}, removeEventListener: () => {} }));
afterEach(() => { cleanup(); _reiniciarProjetosParaTestes(); vi.clearAllMocks(); });
const agente = { id: 'bot', conversaId: 'c1', projetoId: '', nome: 'Bot', funcao: 'Pesquisa', cor: '#56A8FF', tipoMovimento: 'gira' as const, ferramentas: [], status: 'aguardando' as const, verbo: 'Pesquisando', espera: '', instrucoes: '', avulso: true, criadoEm: 1 };
function preparar() { _definirEstadoParaTestes({ ...lerEstado(), agentes: { bot: agente } }); }
function Chat() {
 const e = useProjetos();
 return <>{e.mensagens.map(m => <MensagemChat key={m.id} m={m} agora={0} />)}<MessageComposer placeholder="Mensagem" onSend={texto => { void enviarParaAgente('bot', texto); }} /></>;
}
describe('conversa: envio e carga sob demanda', () => {
 it.each(['/bots/bot', '/grupos/grupo'])('não oferece Compartilhar em %s', rota => {
  render(<MemoryRouter initialEntries={[rota]}><AppShell titulo="Conversa">Conteúdo</AppShell></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'Compartilhar' })).toBeNull();
 });
 it('não oferece avaliações sem rota', () => {
  render(<MensagemChat m={{ id: 'm', conversaId: 'c', autor: 'sora', texto: 'Resposta', criadoEm: 1 }} agora={0} />);
  expect(screen.queryByRole('button', { name: 'Boa resposta' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Resposta ruim' })).toBeNull();
 });
 it('Enter mostra a bolha e Enviando antes de o POST resolver, sem esperar 100 ms', async () => {
  preparar(); mock.post.mockReturnValue(new Promise(() => {})); render(<Chat />);
  const campo = screen.getByRole('textbox', { name: 'Mensagem' });
  fireEvent.change(campo, { target: { value: 'Pesquisar agora' } });
  const inicio = performance.now(); fireEvent.keyDown(campo, { key: 'Enter', code: 'Enter' });
  expect(screen.getByText('Pesquisar agora', { selector: '.user-message' })).toBeTruthy();
  expect(screen.getByText('Enviando…')).toBeTruthy();
  expect(performance.now() - inicio).toBeLessThan(100);
  await act(async () => {});
 });
 it('falha mantém a pergunta e permite tentar de novo sem duplicar', async () => {
  preparar(); mock.post.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ mensagem_id: 'real' });
  await enviarParaAgente('bot', 'Pergunta');
  expect(lerEstado().mensagens[0]?.envio).toBe('erro');
  render(<MensagemChat m={lerEstado().mensagens[0]!} agora={0} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Tentar de novo' })); });
  expect(lerEstado().mensagens).toHaveLength(1); expect(lerEstado().mensagens[0]?.id).toBe('real');
 });
 it('eco SSE antes do POST é reconciliado pelo id, mantendo duas perguntas iguais', async () => {
  preparar(); mock.post.mockImplementation(async () => {
   _aplicarEventoParaTestes({ id: '1', tipo: 'mensagem.inicio', dados: { conversa_id: 'c1', mensagem_id: 'real', autor: 'usuario' }, recebidoEm: Date.now() });
   _aplicarEventoParaTestes({ id: '2', tipo: 'mensagem.delta', dados: { conversa_id: 'c1', mensagem_id: 'real', texto: 'Igual' }, recebidoEm: Date.now() });
   return { mensagem_id: 'real' };
  });
  await enviarParaAgente('bot', 'Igual');
  expect(lerEstado().mensagens).toHaveLength(1); expect(lerEstado().mensagens[0]?.texto).toBe('Igual');
  mock.post.mockResolvedValueOnce({ mensagem_id: 'real2' }); await enviarParaAgente('bot', 'Igual');
  expect(lerEstado().mensagens).toHaveLength(2);
 });
 it('primeira conversa da Sora também nasce antes da rede; repetir confirmação não repete POST', async () => {
  mock.post.mockResolvedValue({ id: 'nova', tipo: 'chat', titulo: 'Oi', criada_em: '2026-11-14T12:00:00Z', atualizada_em: '2026-11-14T12:00:00Z' });
  mock.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([{ id: 'real', conversa_id: 'nova', autor: 'usuario', conteudo: 'Oi', anexos: [], criada_em: '2026-11-14T12:00:00Z' }]);
  const envio = conversarComSora('Oi'); expect(lerEstado().mensagens[0]?.envio).toBe('enviando'); await envio;
  await tentarEnvioNovamente(lerEstado().mensagens[0]!.id);
  expect(mock.post).toHaveBeenCalledTimes(1); expect(lerEstado().mensagens[0]?.id).toBe('real');
 });
 it('inicializa com só duas consultas e nenhum histórico ou entrega', async () => {
  mock.get.mockResolvedValue([]); await iniciarProjetos();
  expect(mock.get.mock.calls.map(c => c[0])).toEqual(['/v1/conversas', '/v1/agentes']);
 });
 it('carrega só a conversa aberta; anteriores usa timestamp antes e preserva SSE', async () => {
  const lista = Array.from({ length: 50 }, (_, i) => ({ id: 'm'+i, conversa_id: 'c1', autor: 'usuario', conteudo: 'Mensagem', anexos: [], criada_em: new Date(1700000000000+i*1000).toISOString() }));
  mock.get.mockResolvedValueOnce(lista).mockResolvedValueOnce([{ ...lista[0], id: 'antiga', criada_em: '2020-01-01T00:00:00Z' }]);
  await carregarMensagens('c1'); await carregarMensagens('c1'); expect(mock.get).toHaveBeenCalledTimes(1);
  await carregarMensagens('c1', true);
  expect(mock.get.mock.calls[1]?.[0]).toContain('antes='+encodeURIComponent(lista[0]!.criada_em));
  expect(lerEstado().mensagens).toHaveLength(51);
 });
});

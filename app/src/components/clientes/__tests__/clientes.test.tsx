import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { canaisEmpresa, type ConexaoEmpresa, type SugestaoEmpresa } from '../../../api/canaisEmpresa';
import { ErroApi } from '../../../api/cliente';
import { CanaisEmpresa } from '../../settings/CanaisEmpresa';
import { Ficha } from '../Ficha';
import { Aprendizado, CartaoSugestao } from '../Aprendizado';
import { Autorizacoes } from '../Autorizacoes';
import Clientes from '../../../screens/Clientes';
import { receberEventoClientes } from '../../../state/clientes';
import { Origem, useConsulta } from '../comum';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span /> }));
vi.mock('../../layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('../../../state/bots', () => ({ useBots: () => [{ id: 'b1', nome: 'Atendimento' }] }));
vi.mock('../../../state/grupos', () => ({ useGrupos: () => ({ lista: [{ id: 'g1', nome: 'Comercial' }] }) }));
vi.mock('../../../state/atencao', () => ({ carregarPrecisaDeVoce: vi.fn().mockResolvedValue(undefined) }));

const conexao: ConexaoEmpresa = { canal: 'slack', configurada: true, rotulo: '', ativa: true, config: {}, segredos_definidos: { bot_token: true, signing_secret: true }, canais_escolhidos: [], webhook_caminho: '/v1/canais-empresa/webhooks/slack/1', escopos_slack: ['channels:read'] };
const ficha = { id: 'c1', nome: 'Cliente QA', canal: 'slack' as const, id_externo: 'UQA', papel: 'cliente', ultima_mensagem_em: null, total_fatos: 1, fatos: [{ id: 'f1', tipo: 'preferencia' as const, texto: 'Prefere entrega à tarde', data_referencia: '2026-11-16', origem_canal: 'slack', origem_link: 'https://exemplo.slack.com/a', origem_externo_id: null, criado_em: '2026-11-15', editado: false }] };
const sugestao: SugestaoEmpresa = { id: 's1', agente_id: 'b1', tipo: 'instrucoes', titulo: 'Melhorar atendimento', motivo: 'Pergunta frequente', texto: 'Informe o prazo de entrega.', habilidade_nome: null, conhecimento_ids: ['k1'], status: 'pendente', aprovacao_id: 'a1', criada_em: '2026-11-15', decidida_em: null, desfeita_em: null };

beforeEach(() => { vi.restoreAllMocks(); });
describe('sugestão de melhoria', () => {
  it('nunca oferece "Sempre permitir"', () => {
    render(<CartaoSugestao sugestao={sugestao} nomeBot="Atendimento" onAtualizar={() => undefined} />);
    expect(screen.queryByRole('button', { name: /Sempre permitir/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeTruthy();
  });
});
describe('canais da empresa', () => {
  it('omite segredos vazios na edição e apaga os campos após salvar', async () => {
    vi.spyOn(canaisEmpresa, 'conexoes').mockResolvedValue([conexao]);
    vi.spyOn(canaisEmpresa, 'preferencias').mockResolvedValue({ retencao_dias: 90, sugestoes_intervalo_dias: 7, ultima_analise_em: null });
    const salvar = vi.spyOn(canaisEmpresa, 'salvarConexao').mockResolvedValue(conexao);
    render(<CanaisEmpresa />);
    const token = await screen.findByLabelText('Token do bot');
    expect((token as HTMLInputElement).value).toBe('');
    fireEvent.change(token, { target: { value: 'token-novo-qa' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar conexão' }));
    await waitFor(() => expect(salvar).toHaveBeenCalledWith('slack', { segredos: { bot_token: 'token-novo-qa' }, config: { dominio: '', ids_funcionarios: [] } }));
    await waitFor(() => expect((token as HTMLInputElement).value).toBe(''));
    expect(screen.queryByText('token-novo-qa')).toBeNull();
    expect(screen.getByText(/Nunca envia mensagens/)).toBeTruthy();
  });
  it('mostra falha do teste mesmo com HTTP 200 e conserva os avisos', async () => {
    vi.spyOn(canaisEmpresa, 'conexoes').mockResolvedValue([conexao]);
    vi.spyOn(canaisEmpresa, 'preferencias').mockResolvedValue({ retencao_dias: 90, sugestoes_intervalo_dias: 7, ultima_analise_em: null });
    vi.spyOn(canaisEmpresa, 'testar').mockResolvedValue({ ok: false, detalhe: 'Token com escrita recusado.', avisos: ['Reinstale o app.'] });
    render(<CanaisEmpresa />);
    fireEvent.click(await screen.findByRole('button', { name: 'Testar conexão' }));
    expect(await screen.findByText(/Conexão não validada.*Token com escrita recusado.*Reinstale/)).toBeTruthy();
  });
  it('exige APAGAR antes de excluir cliente e mantém o diálogo se houver erro', async () => {
    vi.spyOn(canaisEmpresa, 'ficha').mockResolvedValue(ficha);
    const apagar = vi.spyOn(canaisEmpresa, 'apagarCliente').mockRejectedValue(new ErroApi(500, 'Falha ao apagar.'));
    render(<Ficha id="c1" onVoltar={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Apagar tudo deste cliente' }));
    const confirmar = screen.getByRole('button', { name: 'Apagar definitivamente' });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Digite APAGAR para confirmar'), { target: { value: 'APAGAR' } });
    fireEvent.click(confirmar);
    await waitFor(() => expect(apagar).toHaveBeenCalledWith('c1'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Falha ao apagar.');
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
  it('salva tipo e remoção explícita da data do fato', async () => {
    vi.spyOn(canaisEmpresa, 'ficha').mockResolvedValue(ficha);
    const salvar = vi.spyOn(canaisEmpresa, 'editarFato').mockResolvedValue(ficha.fatos[0]);
    render(<Ficha id="c1" onVoltar={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Editar fato' }));
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'prazo' } });
    fireEvent.change(screen.getByLabelText('Data de referência'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar fato' }));
    await waitFor(() => expect(salvar).toHaveBeenCalledWith('f1', { texto: 'Prefere entrega à tarde', tipo: 'prazo', data_referencia: null, limpar_data: true }));
  });
  it('edita sugestão sem aplicar e apresenta conflito ao desfazer', async () => {
    const editar = vi.spyOn(canaisEmpresa, 'editarSugestao').mockResolvedValue(sugestao);
    const decidir = vi.spyOn(canaisEmpresa, 'decidirSugestao').mockRejectedValue(new ErroApi(409, 'O bot mudou depois da aplicação.'));
    const atualizou = vi.fn();
    const tela = render(<CartaoSugestao sugestao={sugestao} nomeBot="Atendimento" onAtualizar={atualizou} />);
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText('Texto da sugestão'), { target: { value: 'Novo texto revisado.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar edição' }));
    await waitFor(() => expect(editar).toHaveBeenCalledWith('s1', 'Novo texto revisado.'));
    expect(decidir).not.toHaveBeenCalled();
    await waitFor(() => expect(atualizou).toHaveBeenCalled());
    tela.rerender(<CartaoSugestao sugestao={{ ...sugestao, status: 'aplicada' }} nomeBot="Atendimento" onAtualizar={atualizou} />);
    fireEvent.click(screen.getByRole('button', { name: 'Desfazer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('O bot mudou depois da aplicação.');
  });
  it('revoga clientes preservando o escopo de conhecimento', async () => {
    vi.spyOn(canaisEmpresa, 'autorizacoes').mockResolvedValue([{ alvo_tipo: 'agente', alvo_id: 'b1', escopos: ['clientes', 'conhecimento'] }]);
    const salvar = vi.spyOn(canaisEmpresa, 'autorizar').mockResolvedValue({ alvo_tipo: 'agente', alvo_id: 'b1', escopos: ['conhecimento'] });
    render(<Autorizacoes />);
    const bot = await screen.findByRole('region', { name: 'Atendimento · Bot' });
    fireEvent.click(within(bot).getByLabelText('Fichas de clientes'));
    await waitFor(() => expect(salvar).toHaveBeenCalledWith({ alvo_tipo: 'agente', alvo_id: 'b1', escopos: ['conhecimento'] }));
  });
  it('atualiza listas por SSE sem misturar busca vazia com ausência de clientes', async () => {
    const listar = vi.spyOn(canaisEmpresa, 'clientes').mockResolvedValue([]);
    render(<MemoryRouter><Clientes /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Conectar um canal' })).toHaveAttribute('href', '/configuracoes?secao=canais-empresa');
    act(() => receberEventoClientes({ tipo: 'cliente.atualizado' }));
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('Buscar clientes'), { target: { value: 'Inexistente' } });
    expect(await screen.findByText('Nenhum cliente encontrado.')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Conectar um canal' })).toBeNull();
  });
  const base = { categoria: 'politica' as const, ocorrencias: 4, contraditorio: false, editado: false, anteriores: [], origens: [], primeira_em: '2026-11-14', ultima_em: '2026-11-15' };
  it('conhecimento contraditório mostra a atual e a nova, resolve pela rota e reage ao SSE', async () => {
    const disputado = { ...base, id: 'k1', titulo: 'Trocas', conteudo: 'Prazo de 30 dias', contraditorio: true, estado: 'aprovado' as const, em_disputa: [{ conteudo: 'Prazo de 7 dias', em: '2026-11-14' }] };
    const listar = vi.spyOn(canaisEmpresa, 'conhecimento').mockResolvedValue([]);
    vi.spyOn(canaisEmpresa, 'disputas').mockResolvedValue([disputado]);
    const resolver = vi.spyOn(canaisEmpresa, 'resolverConhecimento').mockResolvedValue(disputado);
    vi.spyOn(canaisEmpresa, 'sugestoes').mockResolvedValue([]);
    render(<Aprendizado />);
    expect(await screen.findByText(/Informações contraditórias/)).toBeTruthy();
    expect(screen.getByText(/Prazo de 30 dias/)).toBeTruthy();
    expect(screen.getByText(/Prazo de 7 dias/)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Para aprovar (1)' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Usar a nova' }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith('k1', 0));
    fireEvent.click(screen.getByRole('button', { name: 'Manter a atual' }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith('k1', null));
    await waitFor(() => expect(listar.mock.calls.length).toBeGreaterThan(2));
  });
  it('item pendente só vale depois de Aprovar; sem resposta não oferece Aprovar; Descartar apaga', async () => {
    const pendente = { ...base, id: 'k2', titulo: 'Frete', conteudo: 'Frete grátis acima de R$ 200', estado: 'pendente' as const, no_prompt: false };
    const semResposta = { ...base, id: 'k3', titulo: 'Horário', conteudo: '', estado: 'pendente' as const, sem_resposta: true };
    vi.spyOn(canaisEmpresa, 'conhecimento').mockImplementation(async (_b, _c, _p, _s, estado) => estado === 'pendente' ? [pendente, semResposta] : []);
    vi.spyOn(canaisEmpresa, 'disputas').mockResolvedValue([]);
    vi.spyOn(canaisEmpresa, 'sugestoes').mockResolvedValue([]);
    const aprovar = vi.spyOn(canaisEmpresa, 'aprovarConhecimento').mockResolvedValue(pendente);
    const apagar = vi.spyOn(canaisEmpresa, 'apagarConhecimento').mockResolvedValue(undefined as never);
    render(<Aprendizado />);
    expect(await screen.findByText('Frete grátis acima de R$ 200')).toBeTruthy();
    expect(screen.getByText(/Sem resposta de funcionário ainda/)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Aprovar' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar' }));
    await waitFor(() => expect(aprovar).toHaveBeenCalledWith('k2'));
    fireEvent.click(screen.getAllByRole('button', { name: 'Descartar' })[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar descarte' }));
    await waitFor(() => expect(apagar).toHaveBeenCalledWith('k2'));
  });
  it('descarta respostas antigas e não aceita link de origem executável', async () => {
    let resolver!: (valor: string) => void;
    const atrasada = new Promise<string>(resolve => { resolver = resolve; });
    function Consulta({ chave }: { chave: string }) { const c = useConsulta(chave, () => chave === 'a' ? atrasada : Promise.resolve('Atual')); return <p>{c.dados}</p>; }
    const tela = render(<><Consulta chave="a" /><Origem canal="slack" link="javascript:alert(1)" /></>);
    tela.rerender(<><Consulta chave="b" /><Origem canal="slack" link="javascript:alert(1)" /></>);
    await screen.findByText('Atual');
    await act(async () => { resolver('Antiga'); await atrasada; });
    expect(screen.queryByText('Antiga')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
  });
});

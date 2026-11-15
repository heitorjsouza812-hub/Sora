import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BotResumo } from '../../../state/bots';
import type { PedidoAtencao } from '../../pendencias/tipos';

const bot = (patch: Partial<BotResumo> = {}): BotResumo => ({
  id: 'a1', nome: 'Atlas', cor: '#56A8FF', funcao: 'Pesquisa', estado: 'livre', ferramentas: [], ...patch,
});
const pedido = (patch: Partial<PedidoAtencao> = {}): PedidoAtencao => ({
  id: 'p1', tipo: 'pergunta', titulo: 'Pergunta', resumo: 'texto', ...patch,
});

let ilha: typeof import('../ilhaEstado');
beforeEach(async () => { localStorage.clear(); vi.resetModules(); ilha = await import('../ilhaEstado'); });

describe('visaoIlha com bots, grupos e pedidos de atenção reais', () => {
  it('expõe a Sora fixa, os bonecos e quantos estão trabalhando', () => {
    const bots = [bot({ id: 'a1', estado: 'trabalhando' }), bot({ id: 'a2', nome: 'Luna', cor: '#AC80FF', estado: 'livre' })];
    const visao = ilha.visaoIlha(bots, 0, []);
    expect(visao.sora).toEqual({ nome: 'Sora', cor: '#E2ECFF' });
    expect(visao.bonecos.map(a => ({ id: a.id, estado: a.estado, orb: a.orb }))).toEqual([
      { id: 'a1', estado: 'trabalhando', orb: 'working' },
      { id: 'a2', estado: 'livre', orb: 'idle' },
    ]);
    expect(visao.trabalhando).toBe(1);
  });

  it('traz os pedidos "precisa de você" e os grupos em andamento sem inventar nada', () => {
    const visao = ilha.visaoIlha([bot({ estado: 'precisa_de_voce' })], 2, [pedido()]);
    expect(visao.bonecos[0]!.orb).toBe('listening');
    expect(visao.gruposTrabalhando).toBe(2);
    expect(visao.precisaDeVoce).toEqual([pedido()]);
  });

  it('filtra bonecos por estado e por ocultos', () => {
    const bonecos = ilha.visaoIlha([
      bot({ id: 'a1', estado: 'trabalhando' }),
      bot({ id: 'a2', estado: 'precisa_de_voce' }),
      bot({ id: 'a3', estado: 'livre' }),
    ], 0, []).bonecos;
    expect(ilha.filtrarBonecos(bonecos, { filtro: 'trabalhando', ocultos: [] }).map(a => a.id)).toEqual(['a1']);
    expect(ilha.filtrarBonecos(bonecos, { filtro: 'precisa_de_voce', ocultos: [] }).map(a => a.id)).toEqual(['a2']);
    expect(ilha.filtrarBonecos(bonecos, { filtro: 'todos', ocultos: ['a1'] }).map(a => a.id)).toEqual(['a2', 'a3']);
  });
});

describe('preferências da Ilha', () => {
  it('alterna agente oculto e persiste a preferência', () => {
    ilha.alternarAgenteOculto('a1'); ilha.alternarAgenteOculto('a1'); ilha.alternarAgenteOculto('a2');
    expect(ilha.lerIlhaPrefs().ocultos).toEqual(['a2']);
    expect(JSON.parse(localStorage.getItem('sora.ilha.v1') ?? '{}')).toMatchObject({ ocultos: ['a2'] });
  });

  it('migra preferências antigas (de antes da etapa 5) com os padrões atuais', async () => {
    const antigas = { visivel: false, som: false, esconderOciosa: true, filtro: 'concluidos', projetoId: 'projeto-antigo' };
    localStorage.setItem('sora.ilha.v1', JSON.stringify(antigas)); vi.resetModules(); const migrada = await import('../ilhaEstado');
    expect(migrada.lerIlhaPrefs()).toMatchObject({ visivel: false, som: false, esconderOciosa: true, ocultos: [], ilhaNoApp: false });
  });
});

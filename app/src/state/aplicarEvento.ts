import type { Movimento, PassoTrabalho } from '../types';
import type { RevisaoDominio, AgenteSora, EntregaGerada, EstadoProjetos, Execucao, ProjetoSora, TarefaGerada } from './projetos';
import type { EventoSse } from '../api/eventos';

type Dados = Record<string, unknown>;
const texto = (v: unknown) => typeof v === 'string' ? v : '';
const numero = (v: unknown, padrao = 0) => typeof v === 'number' ? v : padrao;
const lista = (v: unknown) => Array.isArray(v) ? v : [];

function revisaoDominioDe(d: Dados): RevisaoDominio {
  const perfil = (d.perfil && typeof d.perfil === 'object' ? d.perfil : {}) as Dados;
  const opcoes = (lista(d.opcoes) as Dados[]).map(o => ({ rotulo: texto(o.rotulo), valor: (texto(o.valor) === 'negar' ? 'negar' : 'sempre_permitir') as 'negar' | 'sempre_permitir' }));
  return {
    dominio: texto(d.dominio), url: texto(d.url), perfil: { tipo: texto(perfil.tipo), nome: texto(perfil.nome) || null }, agenteId: texto(d.agente_id) || null,
    opcoes: opcoes.length ? opcoes : [{ rotulo: 'Aprovar domínio', valor: 'sempre_permitir' }, { rotulo: 'Negar', valor: 'negar' }],
  };
}

function atualizarProjeto(estado: EstadoProjetos, conversaId: string, fn: (p: ProjetoSora) => ProjetoSora): EstadoProjetos {
  return { ...estado, projetos: estado.projetos.map(p => p.id === conversaId ? fn(p) : p) };
}

function statusDaEtapa(status: string): Execucao['status'] {
  if (status === 'executando') return 'executando';
  if (status === 'concluida') return 'concluida';
  if (status === 'falhou' || status === 'reprovada') return 'falhou';
  if (status === 'cancelada') return 'cancelada';
  return 'pendente';
}

function garantirExecucao(estado: EstadoProjetos, conversaId: string, etapaId: string, agenteId = ''): EstadoProjetos {
  if (estado.execucoes.some(x => x.id === etapaId)) return estado;
  const nova: Execucao = { id: etapaId, agenteId, projetoId: conversaId, tarefaId: etapaId, inicio: Date.now(), roteiro: [], status: 'pendente', progresso: 0 };
  return { ...estado, execucoes: [...estado.execucoes, nova] };
}

/** Redutor único do contrato SSE. É idempotente por id de mensagem, etapa, passo e entrega. */
export function aplicarEvento(estado: EstadoProjetos, evento: EventoSse): EstadoProjetos {
  const d = evento.dados as Dados;
  const conversaId = texto(d.conversa_id) || estado.projetoAtivoId || '';
  if (!conversaId) return estado;

  if (evento.tipo === 'pergunta') {
    const id = texto(d.pergunta_id); if (!id || (estado.pendencias ?? []).some(p => p.id === id)) return estado;
    const opcoes = (lista(d.opcoes) as Dados[]).map(o => ({ rotulo: texto(o.rotulo), valor: texto(o.valor) }));
    return { ...estado, pendencias: [...(estado.pendencias ?? []), { tipo: 'pergunta', id, conversaId, texto: texto(d.texto), opcoes, respostaLivre: d.resposta_livre === true, desde: evento.recebidoEm }] };
  }
  if (evento.tipo === 'aprovacao.pedida') {
    const id = texto(d.aprovacao_id); if (!id || (estado.pendencias ?? []).some(p => p.id === id)) return estado;
    return { ...estado, pendencias: [...(estado.pendencias ?? []), {
      tipo: 'aprovacao', id, conversaId, resumo: texto(d.resumo), dano: texto(d.dano), quemRecebe: texto(d.quem_recebe) || null,
      expiraEm: Date.parse(texto(d.expira_em)) || 0, desde: evento.recebidoEm,
      ...(d.tipo === 'aprovar_dominio' ? { revisaoDominio: revisaoDominioDe(d) } : {}),
    }] };
  }
  if (evento.tipo === 'aprovacao.resolvida') return { ...estado, pendencias: (estado.pendencias ?? []).filter(p => p.id !== texto(d.aprovacao_id)) };

  if (evento.tipo === 'conversa.atualizada') return atualizarProjeto(estado, conversaId, p => ({
    ...p, titulo: texto(d.titulo) || p.titulo, tipo: d.tipo === 'projeto' ? 'projeto' : 'chat',
    aprovadoEm: d.aprovada_versao ? evento.recebidoEm : undefined,
    aprovadaVersao: typeof d.aprovada_versao === 'number' ? d.aprovada_versao : null,
  }));

  if (evento.tipo === 'mensagem.inicio') {
    const id = texto(d.mensagem_id);
    if (!id || estado.mensagens.some(m => m.id === id)) return estado;
    const autorBruto = texto(d.autor);
    const agenteId = texto(d.agente_id) || undefined;
    const autor = autorBruto === 'agente' && agenteId ? agenteId : autorBruto === 'usuario' ? 'usuario' : 'sora';
    return { ...estado, mensagens: [...estado.mensagens, { id, conversaId, autor, agenteId, texto: '', criadoEm: evento.recebidoEm, gerando: true }] };
  }
  if (evento.tipo === 'mensagem.delta') {
    const id = texto(d.mensagem_id);
    // Só quem está gerando recebe delta: mensagem já completa (vinda do histórico ou do `fim`) ficaria
    // com o texto duplicado quando o SSE repete os eventos desde o início.
    return { ...estado, mensagens: estado.mensagens.map(m => m.id === id && m.gerando ? { ...m, texto: m.texto + texto(d.texto) } : m) };
  }
  if (evento.tipo === 'mensagem.fim') {
    const id = texto(d.mensagem_id);
    // A resposta terminou: some o "pensando". Cobre a falha da triagem, em que o backend só publica mensagem.*.
    const fechado = { ...estado, mensagens: estado.mensagens.map(m => m.id === id ? { ...m, gerando: false } : m) };
    return atualizarProjeto(fechado, conversaId, p => p.mensagensPendentes ? { ...p, mensagensPendentes: false } : p);
  }
  if (evento.tipo === 'roteamento') return atualizarProjeto(estado, conversaId, p => ({ ...p, roteamento: texto(d.modo) as ProjetoSora['roteamento'], mensagensPendentes: false }));

  if (evento.tipo === 'agente.criado') {
    const id = texto(d.agente_id); if (!id) return estado;
    const existente = estado.agentes[id];
    const agente: AgenteSora = {
      id, projetoId: conversaId, conversaId: existente?.conversaId,
      nome: texto(d.nome) || existente?.nome || 'Agente', funcao: texto(d.funcao) || existente?.funcao || 'Especialista',
      cor: texto(d.cor) || existente?.cor || '#56A8FF', tipoMovimento: (texto(d.movimento) || existente?.tipoMovimento || 'gira') as Movimento,
      ferramentas: existente?.ferramentas ?? [], status: 'aguardando', verbo: existente?.verbo ?? 'Trabalhando', espera: 'Aguardando',
      instrucoes: existente?.instrucoes ?? '', avulso: d.tipo === 'individual', criadoEm: evento.recebidoEm,
    };
    const proximo = { ...estado, agentes: { ...estado.agentes, [id]: agente } };
    return atualizarProjeto(proximo, conversaId, p => ({ ...p, agenteIds: p.agenteIds.includes(id) ? p.agenteIds : [...p.agenteIds, id] }));
  }

  if (evento.tipo === 'cadeia.criada') {
    const etapas = lista(d.etapas) as Dados[];
    const tarefas: TarefaGerada[] = etapas.map(x => ({ id: texto(x.etapa_id), titulo: texto(x.titulo), ordem: numero(x.ordem), dependeDe: lista(x.depende_de).map(String), agenteId: texto(x.agente_id), status: 'aguardando', progresso: 0 }));
    const novas: Execucao[] = tarefas.filter(t => !estado.execucoes.some(x => x.id === t.id)).map(t => ({
      id: t.id, agenteId: t.agenteId, projetoId: conversaId, tarefaId: t.id, inicio: evento.recebidoEm, status: 'pendente', progresso: 0,
      // O roteiro só recebe o que o backend emitir em eventos `passo`; nada é inventado aqui.
      roteiro: [],
    }));
    const comCadeia = atualizarProjeto(estado, conversaId, p => ({
      // Mesma cadeia reemitida (nova tentativa após reprovação): a etapa nova tem outro id e a MESMA `ordem`;
      // vale a de maior tentativa, ou seja, a mais recente por ordem. Cadeia nova (ajuste) substitui tudo.
      ...p, mensagensPendentes: false, cadeiaId: texto(d.cadeia_id), cadeiaStatus: 'planejando', versao: numero(d.versao, p.versao),
      tarefas: p.cadeiaId === texto(d.cadeia_id) ? [...p.tarefas.filter(t => !tarefas.some(n => n.ordem === t.ordem)), ...tarefas].sort((a, b) => a.ordem - b.ordem) : tarefas,
      agenteIds: tarefas.reduce<string[]>((ids, t) => t.agenteId && !ids.includes(t.agenteId) ? [...ids, t.agenteId] : ids, p.agenteIds),
    }));
    return { ...comCadeia, execucoes: [...comCadeia.execucoes, ...novas] };
  }

  if (evento.tipo === 'etapa.atualizada') {
    const etapaId = texto(d.etapa_id); let proximo = garantirExecucao(estado, conversaId, etapaId);
    const status = statusDaEtapa(texto(d.status)); const progresso = numero(d.progresso);
    proximo = { ...proximo, execucoes: proximo.execucoes.map(x => x.id === etapaId ? { ...x, status, progresso, inicio: status === 'executando' && x.status === 'pendente' ? evento.recebidoEm : x.inicio } : x) };
    return atualizarProjeto(proximo, conversaId, p => ({ ...p, cadeiaStatus: p.cadeiaStatus === 'planejando' ? 'executando' : p.cadeiaStatus, tarefas: p.tarefas.map(t => t.id === etapaId ? {
      ...t, progresso, status: status === 'executando' ? 'trabalhando' : status === 'concluida' ? 'concluido' : status === 'falhou' ? 'erro' : 'aguardando',
    } : t) }));
  }

  if (evento.tipo === 'passo') {
    const etapaId = texto(d.etapa_id); const agenteId = texto(d.agente_id); let proximo = garantirExecucao(estado, conversaId, etapaId, agenteId);
    const passoId = texto(d.passo_id);
    const passo: PassoTrabalho = {
      id: passoId, agenteId, tipo: texto(d.tipo) as PassoTrabalho['tipo'], texto: texto(d.texto), ferramenta: texto(d.ferramenta) || undefined,
      acao: texto(d.acao) || undefined, parametros: d.parametros && typeof d.parametros === 'object' ? d.parametros as Record<string, unknown> : undefined,
      resultado: d.resultado && typeof d.resultado === 'object' ? d.resultado as PassoTrabalho['resultado'] : undefined,
      status: texto(d.status) as PassoTrabalho['status'], inicio: evento.recebidoEm, fim: d.status === 'executando' ? undefined : evento.recebidoEm,
      paraAgenteId: texto(d.para_agente_id) || undefined,
    };
    return { ...proximo, execucoes: proximo.execucoes.map(x => x.id === etapaId ? { ...x, agenteId: agenteId || x.agenteId, roteiro: x.roteiro.some(p => p.id === passoId) ? x.roteiro.map(p => p.id === passoId ? { ...p, ...passo, inicio: p.inicio } : p) : [...x.roteiro, passo] } : x) };
  }

  if (evento.tipo === 'entrega') {
    const id = texto(d.entrega_id); const agenteId = texto(d.agente_id);
    const entrega: EntregaGerada = { id, agenteId, versao: numero(d.versao, 1), tipo: texto(d.tipo) as EntregaGerada['tipo'], titulo: texto(d.titulo), resumo: texto(d.resumo) };
    return atualizarProjeto(estado, conversaId, p => ({ ...p, versao: entrega.versao ?? p.versao, entregas: { ...p.entregas, [agenteId || id]: entrega } }));
  }
  if (evento.tipo === 'cadeia.atualizada' && texto(d.status) !== 'aguardando_usuario') {
    // a cadeia seguiu em frente: perguntas dela já foram respondidas (o backend não emite "pergunta.resolvida")
    estado = { ...estado, pendencias: (estado.pendencias ?? []).filter(p => !(p.tipo === 'pergunta' && p.conversaId === conversaId)) };
  }
  if (evento.tipo === 'cadeia.atualizada') return atualizarProjeto(estado, conversaId, p => ({
    ...p, mensagensPendentes: false, cadeiaStatus: texto(d.status) as ProjetoSora['cadeiaStatus'],
    marcos: d.status === 'concluida' ? { ...p.marcos, fim: evento.recebidoEm } : p.marcos,
  }));
  if (evento.tipo === 'erro') return atualizarProjeto(estado, conversaId, p => ({ ...p, mensagensPendentes: false, erro: texto(d.mensagem) || 'O trabalho foi interrompido.' }));
  return estado;
}

// Apagar com "Desfazer" (item 45): a ação é imediata e um toast oferece desfazer.
// O Modal de confirmação fica só para ações grandes (projeto com vários agentes; e a Sora, que não se apaga).
import { removerAgente, removerProjeto, type EstadoProjetos } from '../../state/projetos';
import { toast } from '../base';
import type { AlvoGestao } from './acoes';

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

/** Ações grandes pedem confirmação; o resto apaga direto com Desfazer. */
export function precisaConfirmar(alvo: AlvoGestao, e: EstadoProjetos) {
  if (alvo.tipo === 'agente') return alvo.id === 'sora';
  const p = e.projetos.find((x) => x.id === alvo.id);
  return !!p && p.agenteIds.filter((id) => e.agentes[id]).length >= 2;
}

/**
 * Apaga e mostra o toast com Desfazer. Devolve `true` se o item apagado estava aberto na tela
 * (quem chamou decide para onde navegar).
 */
export function apagarComDesfazer(alvo: AlvoGestao, e: EstadoProjetos, pathname: string, opcoes: { manterAgentes?: boolean } = {}): boolean {
  if (alvo.tipo === 'projeto') {
    const p = e.projetos.find((x) => x.id === alvo.id);
    if (!p) return false;
    const equipe = p.agenteIds.filter((id) => e.agentes[id]);
    const aberto = pathname.includes(p.id) || (pathname === '/chat/sora' && e.projetoAtivoId === p.id)
      || (!opcoes.manterAgentes && equipe.some((id) => pathname.includes(id)));
    const desfazer = removerProjeto(p.id, opcoes);
    const nome = p.tipo === 'chat' ? 'Chat' : 'Projeto';
    toast({
      mensagem: `${nome} apagado`,
      descricao: `“${p.titulo}”${equipe.length ? (opcoes.manterAgentes ? ` · ${plural(equipe.length, 'agente continua', 'agentes continuam')} como avulso${equipe.length === 1 ? '' : 's'}` : ` e ${plural(equipe.length, 'agente', 'agentes')}`) : ''}`,
      acao: { rotulo: 'Desfazer', onClick: () => { desfazer(); toast({ mensagem: `${nome} restaurado`, tom: 'sucesso', duracao: 3000 }); } },
    });
    return aberto;
  }
  const a = e.agentes[alvo.id];
  if (!a) return false;
  const projetos = e.projetos.filter((p) => p.agenteIds.includes(a.id)).length;
  const aberto = pathname.includes(a.id);
  const desfazer = removerAgente(a.id);
  toast({
    mensagem: 'Agente apagado',
    descricao: `${a.nome} · ${a.funcao}${projetos ? ` — saiu de ${plural(projetos, 'projeto', 'projetos')}` : ''}`,
    acao: { rotulo: 'Desfazer', onClick: () => { desfazer(); toast({ mensagem: `${a.nome} voltou`, tom: 'sucesso', duracao: 3000 }); } },
  });
  return aberto;
}

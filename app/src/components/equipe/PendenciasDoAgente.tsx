// Pendências do agente (Âncora): a lista própria dele ("o que ficou para depois"). Não acorda o agente.
// Status aberta / estacionada / concluída; criar, editar título e notas, trocar status e apagar.
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import * as pecas from '../../state/pecas';
import { mensagemPendencia } from '../../state/pecas';
import type { PendenciaAgente, StatusPendencia } from '../../state/pecas';
import { Button, Input, Textarea } from '../base';
import './equipe.css';

const ROTULO: Record<StatusPendencia, string> = { aberta: 'Aberta', estacionada: 'Estacionada', concluida: 'Concluída' };

function Item({ p, ocupado, aoMudar }: { p: PendenciaAgente; ocupado: boolean; aoMudar: (f: () => Promise<unknown>) => Promise<boolean> }) {
  const [editando, setEditando] = useState(false);
  const [titulo, setTitulo] = useState(p.titulo);
  const [notas, setNotas] = useState(p.notas);
  const salvar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (await aoMudar(() => pecas.alterarPendenciaDoAgente(p.id, { titulo: titulo.trim(), notas }))) setEditando(false);
  };
  if (editando) {
    return (
      <li className="eq-pend" data-status={p.status}>
        <form onSubmit={ev => void salvar(ev)} className="eq-pend-form" aria-label={`Editar pendência ${p.titulo}`}>
          <Input rotulo="Título" value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={200} />
          <Textarea rotulo="Notas" value={notas} onChange={e => setNotas(e.target.value)} rows={3} maxLength={4000} />
          <span className="eq-item-acoes">
            <Button type="submit" tamanho="M" variante="primario" disabled={!titulo.trim() || ocupado}>Salvar</Button>
            <Button type="button" tamanho="M" variante="secundario" onClick={() => { setEditando(false); setTitulo(p.titulo); setNotas(p.notas); }}>Cancelar</Button>
          </span>
        </form>
      </li>
    );
  }
  return (
    <li className="eq-pend" data-status={p.status}>
      <span className="eq-pend-texto"><strong>{p.titulo}</strong>{p.notas && <p>{p.notas}</p>}</span>
      <span className="eq-item-acoes">
        <select aria-label={`Status de ${p.titulo}`} value={p.status} disabled={ocupado} onChange={e => void aoMudar(() => pecas.alterarPendenciaDoAgente(p.id, { status: e.target.value as StatusPendencia }))}>
          {(Object.keys(ROTULO) as StatusPendencia[]).map(s => <option key={s} value={s}>{ROTULO[s]}</option>)}
        </select>
        <button type="button" onClick={() => setEditando(true)}>Editar</button>
        <button type="button" disabled={ocupado} onClick={() => void aoMudar(() => pecas.apagarPendenciaDoAgente(p.id))}>Apagar</button>
      </span>
    </li>
  );
}

export function PendenciasDoAgente({ agenteId }: { agenteId: string }) {
  const [itens, setItens] = useState<PendenciaAgente[] | null>(null);
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [titulo, setTitulo] = useState('');
  const [notas, setNotas] = useState('');
  const [estacionar, setEstacionar] = useState(false);

  const recarregar = useCallback(() => pecas.listarPendenciasDoAgente(agenteId).then(setItens), [agenteId]);
  useEffect(() => { recarregar().catch(e => { setErro(mensagemPendencia(e)); setItens(l => l ?? []); }); }, [recarregar]);

  /** Roda a mudança, recarrega a lista e mostra o erro (409 com a mensagem do limite). */
  const mudar = async (f: () => Promise<unknown>): Promise<boolean> => {
    setOcupado(true); setErro('');
    try { await f(); await recarregar(); return true; } catch (e) { setErro(mensagemPendencia(e)); return false; } finally { setOcupado(false); }
  };
  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (await mudar(() => pecas.criarPendenciaDoAgente(agenteId, { titulo: titulo.trim(), notas, status: estacionar ? 'estacionada' : 'aberta' }))) { setTitulo(''); setNotas(''); setEstacionar(false); }
  };

  const grupo = (s: StatusPendencia) => (itens ?? []).filter(p => p.status === s);
  const abertas = grupo('aberta').length + grupo('estacionada').length;
  return (
    <section className="eq-pendencias" aria-label="Pendências do agente">
      <div className="progress-title"><span>Pendências</span><b>{abertas}</b></div>
      <form className="eq-pend-novo" onSubmit={ev => void criar(ev)} aria-label="Criar pendência">
        <Input rotulo="Nova pendência" value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={200} placeholder="O que ficou para depois?" />
        <Textarea rotulo="Notas (opcional)" value={notas} onChange={e => setNotas(e.target.value)} rows={2} maxLength={4000} />
        <label className="eq-membro"><input type="checkbox" checked={estacionar} onChange={e => setEstacionar(e.target.checked)} />Criar como estacionada</label>
        <Button type="submit" tamanho="M" variante="secundario" disabled={!titulo.trim() || ocupado}>Adicionar pendência</Button>
      </form>
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
      {itens === null ? <p className="eq-nota" role="status">Carregando pendências…</p> : !itens.length ? <p className="eq-nota">Nenhuma pendência.</p> : <>
        {(['aberta', 'estacionada'] as const).map(s => grupo(s).length > 0 && (
          <div key={s} className="eq-pend-grupo"><h4>{ROTULO[s]}s ({grupo(s).length})</h4><ul>{grupo(s).map(p => <Item key={p.id} p={p} ocupado={ocupado} aoMudar={mudar} />)}</ul></div>
        ))}
        {grupo('concluida').length > 0 && (
          <details className="eq-pend-grupo"><summary>Concluídas ({grupo('concluida').length})</summary><ul>{grupo('concluida').map(p => <Item key={p.id} p={p} ocupado={ocupado} aoMudar={mudar} />)}</ul></details>
        )}
      </>}
    </section>
  );
}

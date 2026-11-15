import { useSyncExternalStore } from 'react';

// O receptor global só invalida consultas. Dados pessoais ficam nas telas autenticadas,
// nunca em cache global/localStorage; respostas de telas desmontadas são descartadas.
let revisao = { clientes: 0, conhecimento: 0 };
const ouvintes = new Set<() => void>();
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
export const lerRevisaoClientes = () => revisao;
export const useRevisaoClientes = () => useSyncExternalStore(assinar, lerRevisaoClientes, lerRevisaoClientes);
export function receberEventoClientes(evento: { tipo: string }) {
  if (evento.tipo === 'cliente.atualizado') revisao = { ...revisao, clientes: revisao.clientes + 1 };
  else if (evento.tipo === 'conhecimento.atualizado') revisao = { ...revisao, conhecimento: revisao.conhecimento + 1 };
  else return;
  ouvintes.forEach(fn => fn());
}

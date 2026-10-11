// Estados de erro derivados do navegador + simulação: conexão e créditos.
import { useCallback, useSyncExternalStore } from 'react';
import { resumoCreditos, useCreditos } from '../../state/creditos';
import { definirErroSimulado, lerErroSimulado, useErroSimulado } from './simulacao';

const assinarRede = (f: () => void) => {
  window.addEventListener('online', f);
  window.addEventListener('offline', f);
  return () => { window.removeEventListener('online', f); window.removeEventListener('offline', f); };
};
const lerRede = () => (typeof navigator === 'undefined' ? true : navigator.onLine);

/** online/offline (eventos do navegador) ou simulado; tentarDeNovo confere de novo */
export function useConexao() {
  const online = useSyncExternalStore(assinarRede, lerRede, () => true);
  const simulado = useErroSimulado() === 'conexao';
  const tentarDeNovo = useCallback(() => {
    if (lerErroSimulado() === 'conexao') definirErroSimulado(null);
    // força a releitura: dispara o mesmo evento que o navegador dispararia
    window.dispatchEvent(new Event(navigator.onLine ? 'online' : 'offline'));
  }, []);
  return { online: online && !simulado, tentarDeNovo };
}

/** créditos esgotados (store da Brisa) ou simulado */
export function useCreditosEsgotados() {
  const creditos = useCreditos();
  const simulado = useErroSimulado() === 'creditos';
  return simulado || resumoCreditos(creditos).esgotado;
}

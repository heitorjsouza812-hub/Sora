// Janela principal do desktop: liga a ponte do controle do PC (C3) enquanto há alguém logado.
// No navegador e na ilha não faz nada.
import { useEffect } from 'react';
import { useSessao } from '../state/sessao';
import { ligarPontePc } from './computadorPc';

export function PontePc() {
  const logado = useSessao().estado === 'logado';
  useEffect(() => (logado ? ligarPontePc() : undefined), [logado]);
  return null;
}

export default PontePc;

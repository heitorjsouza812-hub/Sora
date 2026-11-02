import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { carregarUso, totalTokens, useUso } from '../../state/uso';
import { Tooltip } from '../base';
import './uso.css';

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD' });
const numero = new Intl.NumberFormat('pt-BR');

export function IndicadorUso() {
  const uso = useUso();
  useEffect(() => { void carregarUso(); }, []);
  const custo = moeda.format(uso.custoTotalUsd);
  const tokens = totalTokens(uso);
  return (
    <Tooltip lado="cima" conteudo={<>
      <strong className="uso-dica-titulo">Uso dos últimos 30 dias</strong>
      {numero.format(tokens)} tokens processados. O valor vem das chamadas registradas pelo backend.
    </>}>
      <Link to="/configuracoes?secao=conta" className="uso-indicador"
        aria-label={`Uso do mês: ${custo}. Abrir configurações da conta`}>
        <span>Uso do mês</span>
        <strong>{uso.carregando ? 'Carregando…' : custo}</strong>
      </Link>
    </Tooltip>
  );
}

// Indicador de créditos no rodapé da barra lateral (item 49, simulado): barra fina + "1.240 de 2.000
// créditos", Tooltip com a explicação e aviso quando restam menos de 10%. Também é quem sincroniza a
// cobrança com o trabalho dos agentes (fica sempre montado na barra lateral).
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Tooltip, toast } from '../base';
import { marcarAvisoCreditos, resumoCreditos, sincronizarCreditos, useCreditos } from '../../state/creditos';
import { useAgora, useProjetos } from '../../state/projetos';
import './creditos.css';

const num = new Intl.NumberFormat('pt-BR');

export function IndicadorCreditos() {
  const projetos = useProjetos();
  const agora = useAgora();
  const c = useCreditos();
  const r = resumoCreditos(c);

  useEffect(() => { sincronizarCreditos(projetos, agora); }, [projetos, agora]);
  useEffect(() => {
    if (!r.acabando || c.avisado) return;
    marcarAvisoCreditos();
    toast({
      mensagem: r.esgotado ? 'Seus créditos acabaram' : 'Seus créditos estão acabando',
      descricao: `Restam ${num.format(r.restantes)} de ${num.format(r.limite)}. Os agentes param quando o saldo zerar (simulação).`,
      tom: 'aviso',
      duracao: 9000,
    });
  }, [r.acabando, r.esgotado, r.restantes, r.limite, c.avisado]);

  const pct = Math.round(r.fracao * 100);
  const texto = `${num.format(r.restantes)} de ${num.format(r.limite)} créditos`;
  return (
    <Tooltip lado="cima" conteudo={<>
      <strong className="cr-dica-titulo">Créditos do Plano Pro (simulação)</strong>
      Cada passo dos agentes consome créditos: ferramentas e entregas custam mais que pensar. O saldo renova todo mês.
      {r.acabando && <> <b>Restam menos de 10%.</b></>}
    </>}>
      <Link to="/configuracoes" className={`cr-indicador${r.acabando ? ' is-acabando' : ''}`}
        aria-label={`Créditos: ${texto} (${pct}%)${r.acabando ? ', acabando' : ''}. Abrir configurações da conta`}>
        <span className="cr-linha" aria-hidden="true">
          <span>{r.acabando ? 'Acabando' : 'Créditos'}</span>
          <span className="cr-valor">{texto}</span>
        </span>
        <span className="cr-barra" aria-hidden="true"><i style={{ width: `${pct}%` }} /></span>
      </Link>
    </Tooltip>
  );
}

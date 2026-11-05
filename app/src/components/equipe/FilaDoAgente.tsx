// Fila de um agente (Tear): itens esperando, pausar/retomar, cancelar e repetir.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { cancelarItemFila, carregarFila, pausarFila, repetirItemFila, retomarFila, useEquipe } from '../../state/equipe';
import { Button } from '../base';
import './equipe.css';

const ROTULO: Record<string, string> = { na_fila: 'Na fila', iniciando: 'Iniciando', rodando: 'Rodando', concluido: 'Concluído', falhou: 'Falhou', cancelado: 'Cancelado', interrompido: 'Interrompido' };

export function FilaDoAgente({ agenteId }: { agenteId: string }) {
  const fila = useEquipe().filas[agenteId];
  const [erro, setErro] = useState('');
  useEffect(() => { void carregarFila(agenteId).catch(() => undefined); }, [agenteId]);
  const agir = async (f: () => Promise<void>) => { setErro(''); try { await f(); } catch (e) { setErro(mensagemDeErro(e)); } };
  if (!fila || (!fila.itens.length && !fila.pausada)) return null;
  return (
    <section className="eq-fila" aria-label="Fila do agente">
      <div className="progress-title"><span>Fila</span><b>{fila.itens.length}</b></div>
      {fila.pausada && <p className="eq-nota" role="status">Fila pausada.</p>}
      <ul>
        {fila.itens.map(i => (
          <li key={i.itemId} data-status={i.status}>
            <span className="eq-previa" title={i.previa}>{i.previa || i.origem}</span>
            <small>{ROTULO[i.status] ?? i.status}{i.esperandoPor ? ` · espera ${i.esperandoPor}` : ''}</small>
            <span className="eq-item-acoes">
              {(i.status === 'falhou' || i.status === 'interrompido') && <button type="button" onClick={() => void agir(() => repetirItemFila(agenteId, i.itemId))}>Repetir</button>}
              {i.status === 'na_fila' && <button type="button" onClick={() => void agir(() => cancelarItemFila(agenteId, i.itemId))}>Cancelar</button>}
            </span>
          </li>
        ))}
      </ul>
      <Button tamanho="M" variante="secundario" onClick={() => void agir(() => fila.pausada ? retomarFila(agenteId) : pausarFila(agenteId))}>{fila.pausada ? 'Retomar fila' : 'Pausar fila'}</Button>
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
    </section>
  );
}

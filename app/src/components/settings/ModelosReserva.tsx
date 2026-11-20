// Modelos reserva da conta: só valem quando um modelo fixo foi escolhido no campo de mensagem e ele
// falha (limite, fora do ar). A Sora tenta estes, nesta ordem, e avisa na conversa. Nunca em silêncio.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { definirReservas, MAX_RESERVAS, obterReservas, type ItemReserva } from '../../api/reservas';
import { modelosAtivos, nomeAmigavelDoModelo, type EstadoModelos } from '../../state/modelos';
import { Button } from '../base';

const chave = (x: ItemReserva) => `${x.provedor_id}::${x.modelo}`;
const doValor = (valor: string): ItemReserva | null => {
  const [provedor_id, ...resto] = valor.split('::');
  return provedor_id && resto.length ? { provedor_id, modelo: resto.join('::') } : null;
};

export function ModelosReserva({ estado }: { estado: EstadoModelos }) {
  const [itens, setItens] = useState<(ItemReserva | null)[]>(Array(MAX_RESERVAS).fill(null));
  const [salvos, setSalvos] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [retorno, setRetorno] = useState('');

  useEffect(() => {
    let vivo = true;
    obterReservas().then(lista => {
      if (!vivo) return;
      setItens(Array.from({ length: MAX_RESERVAS }, (_, i) => lista[i] ?? null));
      setSalvos(lista.map(chave).join('|'));
    }).catch(() => { /* sem lista: começa vazia */ });
    return () => { vivo = false; };
  }, []);

  const opcoes = modelosAtivos(estado).map(({ modelo, definicao }) => ({
    valor: chave({ provedor_id: modelo.provedor_id, modelo: modelo.modelo }),
    rotulo: `${definicao.nome} · ${nomeAmigavelDoModelo(modelo)}`,
  }));
  const escolhidos = itens.filter((x): x is ItemReserva => x !== null);
  const mudou = escolhidos.map(chave).join('|') !== salvos;

  const salvar = async () => {
    setOcupado(true); setRetorno('');
    try {
      const lista = await definirReservas(escolhidos);
      setSalvos(lista.map(chave).join('|'));
      setRetorno(lista.length ? 'Modelos reserva salvos.' : 'Reservas desligadas.');
    } catch (erro) { setRetorno(mensagemDeErro(erro)); }
    finally { setOcupado(false); }
  };

  return <section className="cfg-defaults cfg-reservas">
    <div><span className="cfg-eyebrow">Modelos reserva</span><h2>Se o modelo escolhido falhar</h2>
      <p>Quando você fixa um modelo no campo de mensagem e ele bate no limite ou sai do ar, a Sora tenta estes, nesta ordem, e avisa na conversa. Sem reserva, ela para e pede para você trocar.</p></div>
    {itens.map((item, i) => <label key={i}><span>{i + 1}ª reserva</span>
      <select value={item ? chave(item) : ''} disabled={ocupado} onChange={e => setItens(lista => lista.map((x, j) => j === i ? doValor(e.target.value) : x))}>
        <option value="">Nenhuma</option>
        {opcoes.map(o => <option key={o.valor} value={o.valor} disabled={escolhidos.some(x => chave(x) === o.valor) && (!item || chave(item) !== o.valor)}>{o.rotulo}</option>)}
      </select></label>)}
    <div className="cfg-reservas__acoes"><Button variante="primario" disabled={ocupado || !mudou} carregando={ocupado} onClick={() => { void salvar(); }}>Salvar reservas</Button></div>
    {retorno && <small role="status">{retorno}</small>}
  </section>;
}

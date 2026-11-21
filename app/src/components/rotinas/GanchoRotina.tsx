// Webhook de uma rotina: outro serviço chama a URL assinada e a rotina roda com os dados recebidos.
// O segredo aparece só ao ligar ou ao trocar. Rotina pausada continua respondendo ao webhook.
import { useCallback, useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import {
  alterarGancho, apagarGancho, criarGancho, entregasDoGancho, lerTipos, obterGancho, testarGancho,
  type EntregaGancho, type Gancho,
} from '../../api/ganchos';
import './rotinas.css';

const quando = (iso: string) => new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

function Copiar({ texto, rotulo }: { texto: string; rotulo: string }) {
  const [feito, setFeito] = useState(false);
  const copiar = async () => {
    try { await navigator.clipboard.writeText(texto); setFeito(true); setTimeout(() => setFeito(false), 1500); } catch { /* sem área de transferência: o texto continua selecionável */ }
  };
  return <button type="button" onClick={() => void copiar()} aria-label={`Copiar ${rotulo}`}>{feito ? 'Copiado' : 'Copiar'}</button>;
}

export function GanchoRotina({ rotinaId }: { rotinaId: string }) {
  const [gancho, setGancho] = useState<Gancho | null | undefined>(undefined);
  const [segredo, setSegredo] = useState<string | null>(null);
  const [tipos, setTipos] = useState('');
  const [entregas, setEntregas] = useState<EntregaGancho[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const buscar = useCallback(async () => {
    const atual = await obterGancho(rotinaId);
    return { atual, entregas: atual ? await entregasDoGancho(rotinaId) : [] };
  }, [rotinaId]);
  const aplicar = ({ atual, entregas: lista }: { atual: Gancho | null; entregas: EntregaGancho[] }) => {
    setGancho(atual); setTipos(atual?.tipos_evento.join(', ') ?? ''); setEntregas(lista);
  };
  const carregar = async () => aplicar(await buscar());
  useEffect(() => {
    let vivo = true;
    buscar().then(r => { if (vivo) aplicar(r); }).catch(e => { if (vivo) { setGancho(null); setAviso(mensagemDeErro(e)); } });
    return () => { vivo = false; };
  }, [buscar]);

  const agir = async (f: () => Promise<void>) => {
    setOcupado(true); setAviso(null);
    try { await f(); } catch (e) { setAviso(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const ligarOuTrocar = (lista?: string[]) => agir(async () => {
    const criado = await criarGancho(rotinaId, lista);
    setSegredo(criado.segredo);
    setGancho(criado);
  });

  if (gancho === undefined) return <small className="gancho-carregando">Carregando webhook…</small>;

  return <section className="gancho" aria-label="Webhook da rotina">
    <p className="gancho-titulo"><strong>Webhook</strong>{gancho && <span className={gancho.ativo ? 'rot-estado is-ativa' : 'rot-estado'}>{gancho.ativo ? 'Ligado' : 'Pausado'}</span>}</p>
    {!gancho ? <>
      <small>Outro serviço (loja, formulário, pagamento) chama um endereço e a rotina roda com os dados recebidos. Os dados nunca valem como ordem para o bot.</small>
      <label className="gancho-campo"><span>Só estes tipos de evento (opcional)</span>
        <input value={tipos} onChange={e => setTipos(e.target.value)} placeholder="ex.: pedido.pago, pedido.cancelado" /></label>
      <div className="mem-acoes"><button type="button" disabled={ocupado} onClick={() => void ligarOuTrocar(lerTipos(tipos))}>Ligar webhook</button></div>
    </> : <>
      <div className="gancho-linha"><code>{gancho.url}</code><Copiar texto={gancho.url} rotulo="endereço do webhook" /></div>
      {segredo && <div className="gancho-segredo" role="status">
        <small>Guarde o segredo agora: ele não aparece de novo. Use-o para assinar as chamadas (padrão Standard Webhooks).</small>
        <div className="gancho-linha"><code>{segredo}</code><Copiar texto={segredo} rotulo="segredo do webhook" /></div>
      </div>}
      <label className="gancho-campo"><span>Só estes tipos de evento (vazio = todos)</span>
        <input value={tipos} onChange={e => setTipos(e.target.value)} onBlur={() => {
          const lista = lerTipos(tipos);
          if (lista.join('|') !== gancho.tipos_evento.join('|')) void agir(async () => { setGancho(await alterarGancho(rotinaId, { tipos_evento: lista })); });
        }} placeholder="ex.: pedido.pago" /></label>
      <div className="mem-acoes">
        <button type="button" disabled={ocupado || !gancho.ativo} onClick={() => void agir(async () => {
          const r = await testarGancho(rotinaId);
          setAviso(r.status === 'aceita' ? 'Teste enviado: a rotina vai rodar agora.' : 'Teste recebido, mas o tipo de evento não passou no filtro.');
          await carregar();
        })}>Enviar teste</button>
        <button type="button" disabled={ocupado} onClick={() => void agir(async () => { setGancho(await alterarGancho(rotinaId, { ativo: !gancho.ativo })); })}>{gancho.ativo ? 'Pausar' : 'Retomar'}</button>
        <button type="button" disabled={ocupado} onClick={() => void ligarOuTrocar()}>Trocar segredo</button>
        <button type="button" disabled={ocupado} onClick={() => void agir(async () => { await apagarGancho(rotinaId); setGancho(null); setSegredo(null); setEntregas([]); setTipos(''); })}>Desligar</button>
      </div>
      {entregas.length > 0 && <ul className="gancho-entregas" aria-label="Últimas chamadas recebidas">
        {entregas.slice(0, 5).map(e => <li key={e.id}><span>{quando(e.recebida_em)}</span><span>{e.tipo_evento ?? 'sem tipo'}</span><span>{e.status === 'aceita' ? 'Rodou' : 'Ignorada'}</span></li>)}
      </ul>}
    </>}
    {aviso && <p className="mem-erro" role="status">{aviso}</p>}
  </section>;
}

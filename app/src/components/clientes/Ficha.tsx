import { useState } from 'react';
import { canaisEmpresa, TIPOS_FATO, type FatoCliente } from '../../api/canaisEmpresa';
import { receberEventoClientes, useRevisaoClientes } from '../../state/clientes';
import { Button } from '../base';
import { Modal } from '../overlay';
import { EstadoConsulta, Origem, data, nomeCanal, useAcao, useConsulta } from './comum';

function Fato({ fato, atualizar }: { fato: FatoCliente; atualizar: () => void }) {
  const [editar, setEditar] = useState(false), [apagar, setApagar] = useState(false);
  const [texto, setTexto] = useState(fato.texto), [tipo, setTipo] = useState(fato.tipo), [dia, setDia] = useState(fato.data_referencia ?? '');
  const { ocupado, erro, executar } = useAcao();
  return <article className="ce-faixa"><h3>{TIPOS_FATO[fato.tipo] ?? fato.tipo}</h3><p>{fato.texto}</p>
    <span className="ce-meta">{fato.data_referencia ? `Referência: ${data(fato.data_referencia)} · ` : ''}Registrado em {data(fato.criado_em)}{fato.editado ? ' · Editado por você' : ''}</span>
    <Origem canal={fato.origem_canal} link={fato.origem_link} />
    {fato.origem_externo_id && !fato.origem_link && <small className="ce-meta">Mensagem de origem: {fato.origem_externo_id}</small>}
    {editar ? <form onSubmit={e => { e.preventDefault(); void executar(async () => { await canaisEmpresa.editarFato(fato.id, { texto: texto.trim(), tipo, data_referencia: dia || null, limpar_data: !dia }); atualizar(); setEditar(false); }); }}><fieldset disabled={ocupado} className="ce-campos">
      <label>Tipo<select value={tipo} onChange={e => setTipo(e.target.value as FatoCliente['tipo'])}>{Object.entries(TIPOS_FATO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>Fato<textarea required maxLength={300} value={texto} onChange={e => setTexto(e.target.value)} /></label><label>Data de referência<input type="date" value={dia} onChange={e => setDia(e.target.value)} /></label>
      <div className="ce-acoes"><Button type="submit" variante="primario" disabled={!texto.trim()}>Salvar fato</Button><Button onClick={() => setEditar(false)}>Cancelar</Button></div>
    </fieldset></form> : <div className="ce-acoes"><Button onClick={() => { setTexto(fato.texto); setTipo(fato.tipo); setDia(fato.data_referencia ?? ''); setEditar(true); }}>Editar fato</Button><Button variante="perigo" onClick={() => setApagar(true)}>Apagar fato</Button></div>}
    {erro && <p role="alert">{erro}</p>}
    <Modal open={apagar} onClose={() => { if (!ocupado) setApagar(false); }} title="Apagar este fato?" description="Este fato será removido da ficha." size="sm" footer={<div className="ce-acoes"><Button disabled={ocupado} onClick={() => setApagar(false)}>Cancelar</Button><Button variante="perigo" carregando={ocupado} onClick={() => void executar(async () => { await canaisEmpresa.apagarFato(fato.id); setApagar(false); atualizar(); })}>Confirmar exclusão</Button></div>}><p>{fato.texto}</p>{erro && <p role="alert">{erro}</p>}</Modal>
  </article>;
}
export function Ficha({ id, onVoltar }: { id: string; onVoltar: () => void }) {
  const revisao = useRevisaoClientes();
  const consulta = useConsulta(`${id}:${revisao.clientes}`, signal => canaisEmpresa.ficha(id, signal));
  const [apagar, setApagar] = useState(false), [confirmacao, setConfirmacao] = useState('');
  const { ocupado, erro, executar } = useAcao();
  return <section><Button onClick={onVoltar}>Voltar aos clientes</Button><EstadoConsulta {...consulta} />
    {consulta.dados && <><header className="ce-faixa"><h2>{consulta.dados.nome || consulta.dados.id_externo}</h2><p className="ce-meta">{nomeCanal(consulta.dados.canal)} · {consulta.dados.total_fatos} fatos</p></header>
      {consulta.dados.fatos.map(f => <Fato key={f.id} fato={f} atualizar={() => receberEventoClientes({ tipo: 'cliente.atualizado' })} />)}
      {!consulta.dados.fatos.length && <p>A Sora ainda não extraiu fatos deste atendimento.</p>}
      <div className="ce-faixa"><Button variante="perigo" onClick={() => { setConfirmacao(''); setApagar(true); }}>Apagar tudo deste cliente</Button></div>
    </>}
    <Modal open={apagar} onClose={() => { if (!ocupado) setApagar(false); }} title="Apagar tudo deste cliente?" description="Ação permanente: apaga ficha, mensagens e as contribuições deste cliente ao conhecimento." size="sm" footer={<div className="ce-acoes"><Button disabled={ocupado} onClick={() => setApagar(false)}>Cancelar</Button><Button variante="perigo" disabled={confirmacao !== 'APAGAR'} carregando={ocupado} onClick={() => void executar(async () => { await canaisEmpresa.apagarCliente(id); receberEventoClientes({ tipo: 'cliente.atualizado' }); receberEventoClientes({ tipo: 'conhecimento.atualizado' }); onVoltar(); })}>Apagar definitivamente</Button></div>}>
      <div className="ce-area ce-campos"><p>Se o cliente escrever novamente em um canal selecionado, uma nova ficha poderá ser criada.</p><label>Digite APAGAR para confirmar<input autoComplete="off" value={confirmacao} onChange={e => setConfirmacao(e.target.value)} /></label>{erro && <p role="alert">{erro}</p>}</div>
    </Modal>
  </section>;
}

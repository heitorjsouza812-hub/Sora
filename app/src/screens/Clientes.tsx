import { useState } from 'react';
import { Link } from 'react-router-dom';
import { canaisEmpresa } from '../api/canaisEmpresa';
import { useRevisaoClientes } from '../state/clientes';
import { AppShell } from '../components/layout/AppShell';
import { Button } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { Ficha } from '../components/clientes/Ficha';
import { Aprendizado } from '../components/clientes/Aprendizado';
import { usePendentesConhecimento } from '../components/clientes/usePendentesConhecimento';
import { Autorizacoes } from '../components/clientes/Autorizacoes';
import { EstadoConsulta, Paginacao, nomeCanal, useConsulta } from '../components/clientes/comum';
import '../components/clientes/clientes.css';

function ListaClientes() {
  const [busca, setBusca] = useState(''), [pagina, setPagina] = useState(0), [selecionado, setSelecionado] = useState<string | null>(null);
  const revisao = useRevisaoClientes();
  const consulta = useConsulta(`${busca}:${pagina}:${revisao.clientes}`, signal => canaisEmpresa.clientes(busca, pagina, signal));
  if (selecionado) return <Ficha key={selecionado} id={selecionado} onVoltar={() => setSelecionado(null)} />;
  return <section aria-label="Lista de clientes"><label>Buscar clientes<input type="search" maxLength={120} placeholder="Nome ou contato" value={busca} onChange={e => { setBusca(e.target.value); setPagina(0); }} /></label>
    <EstadoConsulta {...consulta} />
    {consulta.dados && <>{consulta.dados.map(c => <button className="ce-cliente" key={c.id} onClick={() => setSelecionado(c.id)}><span><strong>{c.nome || c.id_externo}</strong><span className="ce-meta">{nomeCanal(c.canal)} · {c.total_fatos} fatos</span></span><span aria-hidden="true">›</span></button>)}
      {!consulta.dados.length && (busca || pagina ? <p>Nenhum cliente encontrado.</p> : <div className="ce-vazio"><SoraOrb size={96} state="idle" decorative /><h2>Conheça melhor seus clientes</h2><p>A Sora reúne o que aprende com os canais de atendimento que você escolher.</p><Button asChild variante="primario"><Link to="/configuracoes?secao=canais-empresa">Conectar um canal</Link></Button></div>)}
      {(pagina > 0 || consulta.dados.length >= 50) && <Paginacao pagina={pagina} quantidade={consulta.dados.length} onPagina={setPagina} />}
    </>}
  </section>;
}
export default function Clientes() {
  const [aba, setAba] = useState('clientes');
  const { total: pendentes } = usePendentesConhecimento();
  return <AppShell titulo="Clientes" acoes={<span />}><main className="ce-page"><div className="ce-coluna ce-area">
    <nav className="ce-abas" aria-label="Seções de clientes">{[['clientes', 'Fichas de clientes'], ['conhecimento', 'O que a Sora aprendeu'], ['autorizacoes', 'Quem pode consultar']].map(([id, nome]) => <Button key={id} variante="fantasma" aria-pressed={aba === id} onClick={() => setAba(id)}>{nome}{id === 'conhecimento' && pendentes > 0 && <span className="ce-contador" aria-label={`${pendentes} para aprovar`}>{pendentes}</span>}</Button>)}</nav>
    {aba === 'clientes' ? <ListaClientes /> : aba === 'conhecimento' ? <Aprendizado /> : <Autorizacoes />}
  </div></main></AppShell>;
}

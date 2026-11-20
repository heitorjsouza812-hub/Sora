import { CanaisEmpresa } from '../components/settings/CanaisEmpresa';
import { NotificacoesDesktop } from '../components/settings/NotificacoesDesktop';
import { ComputadorPC } from '../components/settings/ComputadorPC';
import { TrocarSenha } from '../components/settings/TrocarSenha';
import { ModelosReserva } from '../components/settings/ModelosReserva';
import { MeusDados } from '../components/settings/MeusDados';
import { RelatosEnviados } from '../components/relatos/RelatosEnviados';
import { VersaoApp } from '../components/settings/VersaoApp';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Button } from '../components/base';
import { Modal } from '../components/overlay';
import { ModelDefaults, ProviderCard } from '../components/settings';
import { SecaoConectores, SecaoHabilidades, SecaoMemoria, SecaoNavegador, SecaoRotinas, SecaoTelegram } from '../components/settings/SecoesPecas';
import '../components/settings/settings.css';
import { definirIlhaPrefs, useIlhaPrefs, type FiltroBots } from '../components/ilha/ilhaEstado';
import { abrirIlha, fecharIlha } from '../components/ilha/ilhaUi';
import { tocar } from '../components/ilha/som';
import '../components/ilha/ilha-partes.css';
import { desconectarTodosProvedores, PROVEDORES_MODELO, useModelos } from '../state/modelos';
import { limparTudo } from '../state/projetos';
import { carregarUso, totalTokens, useUso } from '../state/uso';
import { mensagemDeErro } from '../api/cliente';
import { apagarConta } from '../state/sessao';

type Secao = 'canais-empresa' | 'modelos' | 'memoria' | 'rotinas' | 'conectores' | 'habilidades' | 'navegador' | 'telegram' | 'ilha' | 'computador' | 'conta';
const SECOES: { id: Secao; rotulo: string }[] = [
  { id: 'modelos', rotulo: 'Modelos de IA' },
  { id: 'canais-empresa', rotulo: 'Canais da empresa' },
  { id: 'memoria', rotulo: 'Memória' },
  { id: 'rotinas', rotulo: 'Rotinas' },
  { id: 'habilidades', rotulo: 'Habilidades' },
  { id: 'conectores', rotulo: 'Conectores' },
  { id: 'navegador', rotulo: 'Navegador' },
  { id: 'telegram', rotulo: 'Telegram' },
  { id: 'ilha', rotulo: 'Ilha' },
  { id: 'computador', rotulo: 'Computador' },
  { id: 'conta', rotulo: 'Conta' },
];

function ConfiguracaoIlha() {
  const prefs = useIlhaPrefs();
  const alternarVisibilidade = (visivel: boolean) => {
    definirIlhaPrefs({ visivel });
    if (visivel) abrirIlha(); else fecharIlha();
  };
  return <>
    <header className="cfg-heading"><h2>Ilha da Sora</h2><p>No computador, acompanhe quem está trabalhando e o que precisa de você fora do app — a ilha aparece no topo da tela quando a Sora sai de foco (minimizada ou em segundo plano) e some quando você volta a ela.</p></header>
    <div className="cfg-ilha"><NotificacoesDesktop />
      <label className="cfg-ilha__linha"><span><strong>Mostrar ilha</strong><small>Liga a ilha fora do app; dentro do app e no navegador ela nunca aparece.</small></span><span className="cfg-switch"><input type="checkbox" role="switch" aria-checked={prefs.visivel} checked={prefs.visivel} onChange={(e) => alternarVisibilidade(e.target.checked)} /><span aria-hidden="true" /></span></label>
      <label className="cfg-ilha__linha"><span><strong>Sons</strong><small>Avisos discretos ao abrir, um bot concluir e um pedido novo chegar.</small></span><span className="cfg-switch"><input type="checkbox" role="switch" aria-checked={prefs.som} checked={prefs.som} onChange={(e) => definirIlhaPrefs({ som: e.target.checked })} /><span aria-hidden="true" /></span></label>
      <label className="cfg-ilha__linha"><span><strong>Recolher quando nada roda</strong><small>Deixa apenas uma faixa fina até você passar o mouse no topo.</small></span><span className="cfg-switch"><input type="checkbox" role="switch" aria-checked={prefs.esconderOciosa} checked={prefs.esconderOciosa} onChange={(e) => definirIlhaPrefs({ esconderOciosa: e.target.checked })} /><span aria-hidden="true" /></span></label>
      <label className="cfg-ilha__linha"><span><strong>Filtro padrão</strong><small>Quais bots aparecem na ilha. Dá para trocar também direto na ilha.</small></span><select value={prefs.filtro} onChange={(e) => definirIlhaPrefs({ filtro: e.target.value as FiltroBots })}><option value="todos">Todos</option><option value="trabalhando">Trabalhando</option><option value="precisa_de_voce">Precisa de você</option></select></label>
      <div className="cfg-ilha__acoes"><Button onClick={() => tocar('abrir')} disabled={!prefs.som}>Testar som</Button></div>
    </div>
  </>;
}

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD' });
const numero = new Intl.NumberFormat('pt-BR');

function UsoDaConta() {
  const uso = useUso();
  useEffect(() => { void carregarUso(); }, []);
  return <section className="cfg-plano" aria-labelledby="cfg-uso-titulo">
    <div className="cfg-plano__topo"><div><span className="cfg-eyebrow">Últimos 30 dias</span><h3 id="cfg-uso-titulo">Uso do mês</h3></div><strong>{moeda.format(uso.custoTotalUsd)}</strong></div>
    {uso.carregando && <p role="status">Carregando uso…</p>}
    {uso.erro && <p role="alert">{uso.erro}</p>}
    {!uso.carregando && !uso.erro && <p>{numero.format(totalTokens(uso))} tokens processados em {numero.format(uso.itens.length)} grupo(s) de chamadas de modelo.</p>}
    <p>Os valores vêm das chamadas registradas pelo backend e podem variar conforme o provedor e o modelo.</p>
  </section>;
}

export default function Configuracoes() {
  const [params] = useSearchParams();
  const [secao, setSecao] = useState<Secao>(() => SECOES.find(s => s.id === params.get('secao'))?.id ?? 'modelos');
  const [confirmarLimpeza, setConfirmarLimpeza] = useState(false);
  const [apagandoDados, setApagandoDados] = useState(false);
  const [erroLimpeza, setErroLimpeza] = useState('');
  const [confirmarChaves, setConfirmarChaves] = useState(false);
  const [confirmarConta, setConfirmarConta] = useState(false);
  const [senhaConta, setSenhaConta] = useState('');
  const [erroConta, setErroConta] = useState('');
  const estado = useModelos();
  const nav = useRef<HTMLDivElement>(null);
  const [bordas, setBordas] = useState({ inicio: false, fim: false });
  const medirAbas = () => { const el = nav.current; if (el) setBordas({ inicio: el.scrollLeft > 2, fim: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 }); };
  useEffect(() => {
    nav.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    medirAbas();
    const el = nav.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(medirAbas); observer.observe(el);
    return () => observer.disconnect();
  }, [secao]);
  const conectados = PROVEDORES_MODELO.some(p => !!estado.provedores[p.id].conexao);
  const provedores = [...PROVEDORES_MODELO].sort((a, b) => Number(!!estado.provedores[b.id].conexao) - Number(!!estado.provedores[a.id].conexao));
  const navigate = useNavigate();
  // setas/Home/End entre as abas (padrão WAI-ARIA de tablist)
  const teclaAba = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = SECOES.findIndex(s => s.id === secao);
    const proximo = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? (i + 1) % SECOES.length
      : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? (i - 1 + SECOES.length) % SECOES.length
      : e.key === 'Home' ? 0 : e.key === 'End' ? SECOES.length - 1 : -1;
    if (proximo < 0) return;
    e.preventDefault();
    setSecao(SECOES[proximo].id);
    e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[proximo]?.focus();
  };
  return <AppShell titulo="Configurações" acoes={<span />}><main className="cfg-page">
    <div className="cfg-shell">
      <aside className="cfg-nav" data-inicio={bordas.inicio} data-fim={bordas.fim}><div ref={nav} onScroll={medirAbas} role="tablist" aria-label="Seções das configurações" aria-orientation="vertical" onKeyDown={teclaAba}>
        {SECOES.map(s => <button key={s.id} id={`cfg-aba-${s.id}`} role="tab" aria-selected={secao === s.id} aria-controls="cfg-painel" tabIndex={secao === s.id ? 0 : -1} onClick={() => setSecao(s.id)}>{s.rotulo}</button>)}
      </div></aside>
      <section className="cfg-main" id="cfg-painel" role="tabpanel" aria-labelledby={`cfg-aba-${secao}`}>
        {secao === 'modelos' ? <><header className="cfg-heading"><h2>Modelos de IA</h2><p>Conecte os provedores que a Sora e seus bots podem usar. Você escolhe o modelo padrão e pode personalizar cada bot.</p></header>
          {estado.carregando && <div className="cfg-loading" role="status">Carregando provedores e modelos…</div>}
          {estado.erro && <div className="cfg-error" role="alert">{estado.erro}</div>}
          {conectados && <ModelDefaults estado={estado} />}
          {conectados && <ModelosReserva estado={estado} />}
          <div className="cfg-provider-grid">{provedores.map(p => <ProviderCard key={p.id} provedor={p} />)}</div>
          {!conectados && <ModelDefaults estado={estado} />}
          <section className="cfg-security"><h3>Segurança das suas chaves</h3><p>As chaves são enviadas ao backend da Sora e guardadas cifradas. O navegador recebe apenas os últimos caracteres para identificação.</p><Button className="cfg-btn-perigo" onClick={() => setConfirmarChaves(true)}>Desconectar todas as APIs</Button></section>
        </> : secao === 'canais-empresa' ? <CanaisEmpresa /> : secao === 'memoria' ? <SecaoMemoria /> : secao === 'rotinas' ? <SecaoRotinas /> : secao === 'habilidades' ? <SecaoHabilidades /> : secao === 'conectores' ? <SecaoConectores /> : secao === 'navegador' ? <SecaoNavegador /> : secao === 'telegram' ? <SecaoTelegram /> : secao === 'ilha' ? <ConfiguracaoIlha /> : secao === 'computador' ? <ComputadorPC /> : secao === 'conta' ? <><header className="cfg-heading"><h2>Conta</h2><p>Gerencie os dados da sua conta.</p></header><UsoDaConta /><TrocarSenha /><MeusDados /><RelatosEnviados /><VersaoApp /><h3 className="cfg-danger-title">Zona de perigo</h3><section className="cfg-account"><div><h3>Dados da Sora</h3><p>Apague grupos, conversas e bots. As conexões de modelos não serão alteradas.</p></div><Button className="cfg-btn-perigo" onClick={() => setConfirmarLimpeza(true)}>Apagar todos os dados</Button></section><section className="cfg-account"><div><h3>Apagar conta</h3><p>Remove permanentemente a conta, as chaves cifradas e os dados guardados no servidor.</p></div><Button variante="fantasma" className="cfg-btn-perigo" onClick={() => setConfirmarConta(true)}>Apagar conta</Button></section></> : null}
      </section>
    </div>
    <Modal open={confirmarLimpeza} onClose={() => { if (!apagandoDados) setConfirmarLimpeza(false); }} title="Apagar todos os dados?" description="Esta ação não pode ser desfeita." size="sm" footer={<div className="cfg-modal-actions"><Button disabled={apagandoDados} onClick={() => setConfirmarLimpeza(false)}>Cancelar</Button><Button variante="perigo" carregando={apagandoDados} onClick={() => { setErroLimpeza(''); setApagandoDados(true); void limparTudo().then(() => { setConfirmarLimpeza(false); navigate('/'); }).catch(erro => setErroLimpeza(mensagemDeErro(erro))).finally(() => setApagandoDados(false)); }}>Apagar todos os dados</Button></div>}><p className="cfg-modal-copy">Todos os grupos, chats e bots serão removidos do servidor.</p>{erroLimpeza && <p role="alert">{erroLimpeza}</p>}</Modal>
    <Modal open={confirmarChaves} onClose={() => setConfirmarChaves(false)} title="Desconectar todas as APIs?" description="As conexões e chaves cifradas serão removidas do servidor." size="sm" footer={<div className="cfg-modal-actions"><Button onClick={() => setConfirmarChaves(false)}>Cancelar</Button><Button variante="perigo" onClick={() => { void desconectarTodosProvedores().finally(() => setConfirmarChaves(false)); }}>Desconectar APIs</Button></div>}><p className="cfg-modal-copy">Seus grupos e bots continuam, mas não poderão usar modelos até que uma API seja conectada novamente.</p></Modal>
    <Modal open={confirmarConta} onClose={() => setConfirmarConta(false)} title="Apagar sua conta?" description="Esta ação não pode ser desfeita." size="sm" footer={<div className="cfg-modal-actions"><Button onClick={() => setConfirmarConta(false)}>Cancelar</Button><Button variante="perigo" disabled={!senhaConta} onClick={() => { setErroConta(''); void apagarConta(senhaConta).catch(erro => setErroConta(mensagemDeErro(erro))); }}>Apagar conta</Button></div>}><label className="cfg-delete-account"><span>Confirme sua senha</span><input type="password" value={senhaConta} onChange={e => setSenhaConta(e.target.value)} autoComplete="current-password" />{erroConta && <small role="alert">{erroConta}</small>}</label></Modal>
  </main></AppShell>;
}

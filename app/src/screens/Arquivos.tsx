// Arquivos (Biblioteca, Onda 2): tudo o que você enviou ou que os bots criaram, num lugar só.
// Pastas à esquerda (Todos, Recentes, Favoritos, Sem pasta e as suas), grade com prévia das
// imagens, favorito, mover para pasta, baixar e busca por nome.
import { useEffect, useState, type FormEvent } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { Button, toast } from '../components/base';
import { Modal } from '../components/overlay';
import '../components/settings/settings.css';
import { mensagemDeErro } from '../api/cliente';
import {
  alterarArquivo, apagarPasta, blobDoArquivo, criarPasta, listarArquivos, listarPastas, renomearPasta, tamanhoLegivel,
  type Arquivo, type Pasta, type TipoArquivo, type Vista,
} from '../api/biblioteca';
import '../components/biblioteca/biblioteca.css';

const VISTAS: { id: Vista; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' }, { id: 'recentes', rotulo: 'Recentes' }, { id: 'favoritos', rotulo: 'Favoritos' }, { id: 'sem_pasta', rotulo: 'Sem pasta' },
];
const DATA = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
type Lugar = { vista: Vista; pastaId?: undefined } | { vista?: undefined; pastaId: string };

function extensao(nome: string): string {
  const ponto = nome.lastIndexOf('.');
  return ponto > 0 ? nome.slice(ponto + 1, ponto + 5).toUpperCase() : 'ARQ';
}

function Previa({ arquivo }: { arquivo: Arquivo }) {
  const [url, setUrl] = useState<string | null>(null);
  const imagem = arquivo.tipo.startsWith('image/');
  useEffect(() => {
    if (!imagem) return;
    let vivo = true, criada: string | null = null;
    blobDoArquivo(arquivo.id).then(b => { if (vivo) { criada = URL.createObjectURL(b); setUrl(criada); } }).catch(() => undefined);
    return () => { vivo = false; if (criada) URL.revokeObjectURL(criada); };
  }, [arquivo.id, imagem]);
  return <div className="bib-previa" aria-hidden="true">{imagem && url ? <img src={url} alt="" /> : <span>{extensao(arquivo.nome)}</span>}</div>;
}

async function baixar(arquivo: Arquivo): Promise<void> {
  const url = URL.createObjectURL(await blobDoArquivo(arquivo.id));
  const link = document.createElement('a');
  link.href = url; link.download = arquivo.nome; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Arquivos() {
  const [lugar, setLugar] = useState<Lugar>({ vista: 'todos' });
  const [tipo, setTipo] = useState<TipoArquivo | ''>('');
  const [busca, setBusca] = useState('');
  const [buscaAtiva, setBuscaAtiva] = useState('');
  const [arquivos, setArquivos] = useState<Arquivo[] | null>(null);
  const [proximo, setProximo] = useState<string | null>(null);
  const [pastas, setPastas] = useState<Pasta[]>([]);
  const [novaPasta, setNovaPasta] = useState('');
  const [erro, setErro] = useState<string | null>(null);

  const filtro = { ...lugar, tipo: tipo || undefined, busca: buscaAtiva || undefined };
  const chaveFiltro = JSON.stringify(filtro);

  useEffect(() => {
    let vivo = true;
    listarPastas().then(p => { if (vivo) setPastas(p); }).catch(() => undefined);
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    let vivo = true;
    listarArquivos(JSON.parse(chaveFiltro)).then(p => { if (vivo) { setArquivos(p.itens); setProximo(p.proximo); setErro(null); } })
      .catch(e => { if (vivo) { setArquivos([]); setErro(mensagemDeErro(e)); } });
    return () => { vivo = false; };
  }, [chaveFiltro]);

  const recarregarPastas = () => listarPastas().then(setPastas).catch(() => undefined);
  const mais = async () => {
    if (!proximo) return;
    try { const p = await listarArquivos({ ...filtro, antes: proximo }); setArquivos(a => [...(a ?? []), ...p.itens]); setProximo(p.proximo); }
    catch (e) { toast({ mensagem: mensagemDeErro(e), tom: 'erro' }); }
  };
  const mudar = async (arquivo: Arquivo, patch: { pasta_id?: string | null; favorito?: boolean }) => {
    try {
      const novo = await alterarArquivo(arquivo.id, patch);
      const sai = ('pasta_id' in patch && lugar.pastaId !== undefined && novo.pasta_id !== lugar.pastaId)
        || (patch.favorito === false && lugar.vista === 'favoritos')
        || ('pasta_id' in patch && lugar.vista === 'sem_pasta' && novo.pasta_id !== null);
      setArquivos(a => (a ?? []).flatMap(x => x.id !== arquivo.id ? [x] : sai ? [] : [novo]));
      if ('pasta_id' in patch) void recarregarPastas();
    } catch (e) { toast({ mensagem: mensagemDeErro(e), tom: 'erro' }); }
  };
  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!novaPasta.trim()) return;
    try { await criarPasta(novaPasta); setNovaPasta(''); await recarregarPastas(); }
    catch (e) { toast({ mensagem: mensagemDeErro(e), tom: 'erro' }); }
  };
  const pastaAtual = lugar.pastaId ? pastas.find(p => p.id === lugar.pastaId) : undefined;
  const [dialogo, setDialogo] = useState<'renomear' | 'apagar' | null>(null);
  const [nomeEditado, setNomeEditado] = useState('');
  const [salvando, setSalvando] = useState(false);
  const fecharDialogo = () => { if (!salvando) setDialogo(null); };
  const confirmar = async () => {
    if (!pastaAtual) return;
    setSalvando(true);
    try {
      if (dialogo === 'renomear') {
        if (nomeEditado.trim() && nomeEditado.trim() !== pastaAtual.nome) await renomearPasta(pastaAtual.id, nomeEditado);
      } else {
        await apagarPasta(pastaAtual.id);
        setLugar({ vista: 'todos' });
      }
      await recarregarPastas();
      setDialogo(null);
    } catch (e) { toast({ mensagem: mensagemDeErro(e), tom: 'erro' }); }
    finally { setSalvando(false); }
  };

  const titulo = pastaAtual?.nome ?? VISTAS.find(v => v.id === lugar.vista)?.rotulo ?? 'Arquivos';
  return <AppShell titulo="Arquivos" acoes={<span />}><main className="bib">
    <nav className="bib-lugares" aria-label="Pastas">
      {VISTAS.map(v => <button key={v.id} type="button" aria-current={lugar.vista === v.id ? 'page' : undefined} onClick={() => setLugar({ vista: v.id })}>{v.rotulo}</button>)}
      <span className="bib-separador">Pastas</span>
      {pastas.map(p => <button key={p.id} type="button" aria-current={lugar.pastaId === p.id ? 'page' : undefined} onClick={() => setLugar({ pastaId: p.id })}>{p.nome}<small>{p.total}</small></button>)}
      <form className="bib-nova-pasta" onSubmit={e => void criar(e)}>
        <input aria-label="Nome da nova pasta" placeholder="+ Nova pasta" value={novaPasta} maxLength={60} onChange={e => setNovaPasta(e.target.value)} />
      </form>
    </nav>
    <section className="bib-conteudo" aria-label={titulo}>
      <header className="bib-topo">
        <h1>{titulo}</h1>
        {pastaAtual && <span className="bib-acoes-pasta"><Button tamanho="P" variante="fantasma" onClick={() => { setNomeEditado(pastaAtual.nome); setDialogo('renomear'); }}>Renomear</Button><Button tamanho="P" variante="fantasma" onClick={() => setDialogo('apagar')}>Apagar pasta</Button></span>}
        <form className="bib-filtros" role="search" onSubmit={e => { e.preventDefault(); setBuscaAtiva(busca.trim()); }}>
          <input type="search" aria-label="Buscar arquivos pelo nome" placeholder="Buscar pelo nome…" value={busca} onChange={e => { setBusca(e.target.value); if (!e.target.value) setBuscaAtiva(''); }} />
          <select aria-label="Tipo de arquivo" value={tipo} onChange={e => setTipo(e.target.value as TipoArquivo | '')}>
            <option value="">Todos os tipos</option><option value="imagem">Imagens</option><option value="documento">Documentos</option><option value="outro">Outros</option>
          </select>
        </form>
      </header>
      {erro && <p className="bib-erro" role="alert">{erro}</p>}
      {arquivos === null ? <p role="status">Carregando arquivos…</p>
        : arquivos.length === 0 ? <p className="bib-vazio">{buscaAtiva || tipo ? 'Nenhum arquivo com esse filtro.' : 'Nada aqui ainda. Os arquivos que você enviar e os que os bots criarem aparecem nesta tela.'}</p>
        : <ul className="bib-grade">{arquivos.map(a => <li key={a.id} className="bib-arquivo">
          <Previa arquivo={a} />
          <div className="bib-info"><strong title={a.nome}>{a.nome}</strong><small>{tamanhoLegivel(a.tamanho)} · {DATA.format(new Date(a.criado_em))}{a.origem !== 'usuario' ? ' · feito por um bot' : ''}</small></div>
          <div className="bib-acoes">
            <button type="button" className="bib-estrela" aria-pressed={a.favorito} aria-label={a.favorito ? `Tirar ${a.nome} dos favoritos` : `Marcar ${a.nome} como favorito`} onClick={() => void mudar(a, { favorito: !a.favorito })}>{a.favorito ? '★' : '☆'}</button>
            <select aria-label={`Pasta de ${a.nome}`} value={a.pasta_id ?? ''} onChange={e => void mudar(a, { pasta_id: e.target.value || null })}>
              <option value="">Sem pasta</option>{pastas.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
            <button type="button" aria-label={`Baixar ${a.nome}`} onClick={() => void baixar(a).catch(e => toast({ mensagem: mensagemDeErro(e), tom: 'erro' }))}>Baixar</button>
          </div>
        </li>)}</ul>}
      {proximo && <div className="bib-mais"><Button onClick={() => void mais()}>Carregar mais</Button></div>}
    </section>
    <Modal open={dialogo !== null && !!pastaAtual} onClose={fecharDialogo} size="sm"
      title={dialogo === 'renomear' ? 'Renomear pasta' : `Apagar a pasta "${pastaAtual?.nome ?? ''}"?`}
      description={dialogo === 'apagar' ? 'Os arquivos dela não são apagados: voltam para "Sem pasta".' : undefined}
      footer={<div className="cfg-modal-actions"><Button disabled={salvando} onClick={fecharDialogo}>Cancelar</Button>
        <Button variante={dialogo === 'apagar' ? 'perigo' : 'primario'} carregando={salvando} disabled={dialogo === 'renomear' && !nomeEditado.trim()} onClick={() => void confirmar()}>{dialogo === 'apagar' ? 'Apagar pasta' : 'Salvar'}</Button></div>}>
      {dialogo === 'renomear' && <form onSubmit={e => { e.preventDefault(); void confirmar(); }}>
        <input className="bib-campo-modal" aria-label="Nome da pasta" value={nomeEditado} maxLength={60} autoFocus onChange={e => setNomeEditado(e.target.value)} />
      </form>}
    </Modal>
  </main></AppShell>;
}

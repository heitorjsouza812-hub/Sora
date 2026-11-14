// Memória de um bot: adicionar, editar e esquecer.
import { useEffect, useState, type FormEvent } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { apagarMemoria, criarMemoria, editarMemoria, listarMemoriasDoAgente, type Memoria } from '../../state/pecas';
import './memoria.css';

export function PainelMemoria({ agenteId }: { agenteId: string }) {
  const [itens, setItens] = useState<Memoria[] | null>(null);
  const [novo, setNovo] = useState('');
  const [editando, setEditando] = useState<{ id: string; texto: string } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let ativo = true;
    listarMemoriasDoAgente(agenteId).then(l => { if (ativo) setItens(l); }).catch(e => { if (ativo) { setItens([]); setErro(mensagemDeErro(e)); } });
    return () => { ativo = false; };
  }, [agenteId]);

  const rodar = async (f: () => Promise<void>) => {
    setOcupado(true); setErro(null);
    try { await f(); } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const adicionar = (ev: FormEvent) => {
    ev.preventDefault();
    const texto = novo.trim(); if (!texto) return;
    void rodar(async () => { const m = await criarMemoria(texto, agenteId); setItens(l => [m, ...(l ?? [])]); setNovo(''); });
  };
  const salvar = (ev: FormEvent) => {
    ev.preventDefault();
    if (!editando || !editando.texto.trim()) return;
    const { id, texto } = editando;
    void rodar(async () => { const m = await editarMemoria(id, texto.trim()); setItens(l => (l ?? []).map(x => x.id === id ? m : x)); setEditando(null); });
  };
  const esquecer = (id: string) => void rodar(async () => { await apagarMemoria(id); setItens(l => (l ?? []).filter(x => x.id !== id)); });

  return <section className="painel-mem" aria-label="Memória do bot">
    <p className="eyebrow tools-label">Memória</p>
    {itens === null ? <p className="tools-empty">Carregando…</p> : itens.length === 0 ? <p className="tools-empty">Nada guardado ainda. Peça “lembre que…” na conversa ou adicione abaixo.</p> :
      <ul className="mem-lista">{itens.map(m => <li key={m.id}>
        {editando?.id === m.id ? <form className="mem-edicao" onSubmit={salvar}>
          <textarea aria-label="Editar memória" value={editando.texto} maxLength={500} rows={3} autoFocus onChange={e => setEditando({ id: m.id, texto: e.target.value })} />
          <div><button type="button" onClick={() => setEditando(null)}>Cancelar</button><button type="submit" disabled={ocupado || !editando.texto.trim()}>Salvar</button></div>
        </form> : <>
          <span className="mem-texto">{m.conteudo}</span>
          <span className="mem-acoes">
            <button type="button" onClick={() => setEditando({ id: m.id, texto: m.conteudo })}>Editar</button>
            <button type="button" disabled={ocupado} onClick={() => esquecer(m.id)}>Esquecer</button>
          </span></>}
      </li>)}</ul>}
    <form className="mem-novo" onSubmit={adicionar}>
      <input aria-label="Nova memória" placeholder="Algo que o bot deve lembrar…" value={novo} maxLength={500} onChange={e => setNovo(e.target.value)} />
      <button type="submit" disabled={ocupado || !novo.trim()}>Guardar</button>
    </form>
    {erro && <p className="mem-erro" role="alert">{erro}</p>}
  </section>;
}

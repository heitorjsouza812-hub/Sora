import { useEffect, useRef, useState } from 'react';
import { buscarAutenticado } from '../../api/cliente';
import './mensagens.css';

export function AnexoResposta({ anexo }: { anexo: { id: string; nome: string } }) {
  const [arquivo, setArquivo] = useState<{ url: string; nome: string; imagem: boolean; tamanho: number }>();
  const [erro, setErro] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const dialogo = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const ac = new AbortController(); let url: string | undefined;
    void buscarAutenticado(`/v1/anexos/${anexo.id}`, { signal: ac.signal }).then(async r => {
      const blob = await r.blob(); if (ac.signal.aborted) return;
      const d = r.headers.get('content-disposition') ?? '';
      const bruto = d.match(/filename\*=UTF-8''([^;]+)/i)?.[1] ?? d.match(/filename="?([^";]+)"?/i)?.[1];
      let nome = bruto ?? anexo.nome;
      try { nome = decodeURIComponent(nome); } catch { /* nome literal */ }
      url = URL.createObjectURL(blob);
      setArquivo({ url, nome, imagem: blob.type.startsWith('image/'), tamanho: blob.size });
    }).catch(() => { if (!ac.signal.aborted) setErro(true); });
    return () => { ac.abort(); if (url) URL.revokeObjectURL(url); };
  }, [anexo.id, anexo.nome, tentativa]);
  if (erro) return <button type="button" onClick={() => { setErro(false); setTentativa(x => x + 1); }}>Tentar carregar {anexo.nome} novamente</button>;
  if (!arquivo) return <span role="status">Carregando {anexo.nome}…</span>;
  return <figure className="msg-arquivo">
    {arquivo.imagem && <>
      <button type="button" className="msg-imagem" aria-label={`Ampliar ${arquivo.nome}`} onClick={() => dialogo.current?.showModal()}><img src={arquivo.url} alt={arquivo.nome} loading="lazy" /></button>
      <dialog ref={dialogo} className="msg-imagem-ampliada" aria-label={arquivo.nome}>
        <button type="button" onClick={() => dialogo.current?.close()}>Fechar imagem</button><img src={arquivo.url} alt={arquivo.nome} />
      </dialog>
    </>}
    <figcaption><a href={arquivo.url} download={arquivo.nome}>Baixar {arquivo.nome}</a> <small>{Math.max(1, Math.ceil(arquivo.tamanho / 1024))} KB</small></figcaption>
  </figure>;
}

export function AnexosResposta({ anexos }: { anexos: { id: string; nome: string }[] }) {
  return <div className="msg-anexos-resposta">{anexos.map(a => <AnexoResposta key={a.id} anexo={a} />)}</div>;
}

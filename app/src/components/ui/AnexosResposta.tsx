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
  const kb = `${Math.max(1, Math.ceil(arquivo.tamanho / 1024))} KB`;
  const baixar = (cls: string, rotulo?: string) => <a className={cls} href={arquivo.url} download={arquivo.nome} aria-label={`Baixar ${arquivo.nome}`} title={`Baixar ${arquivo.nome}`}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 11l5 5 5-5M5 20h14" /></svg>{rotulo}
  </a>;
  // Imagem sem moldura: raio de 12 px, "Baixar" como botão de ícone no canto e legenda discreta embaixo.
  if (arquivo.imagem) return <figure className="msg-imagem-fig">
    <div className="msg-imagem-caixa">
      <button type="button" className="msg-imagem" aria-label={`Ampliar ${arquivo.nome}`} onClick={() => dialogo.current?.showModal()}><img src={arquivo.url} alt={arquivo.nome} loading="lazy" /></button>
      {baixar('msg-baixar')}
    </div>
    <figcaption>{arquivo.nome} · {kb}</figcaption>
    <dialog ref={dialogo} className="msg-imagem-ampliada" aria-label={arquivo.nome}>
      <button type="button" onClick={() => dialogo.current?.close()}>Fechar imagem</button><img src={arquivo.url} alt={arquivo.nome} />
    </dialog>
  </figure>;
  return <figure className="msg-arquivo">
    <figcaption>{baixar('msg-arquivo-baixar', arquivo.nome)}<small>{kb}</small></figcaption>
  </figure>;
}

export function AnexosResposta({ anexos }: { anexos: { id: string; nome: string }[] }) {
  return <div className="msg-anexos-resposta">{anexos.map(a => <AnexoResposta key={a.id} anexo={a} />)}</div>;
}

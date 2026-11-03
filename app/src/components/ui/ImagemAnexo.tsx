// Imagem de um anexo (/v1/anexos/{id}): a rota precisa do token, então vira blob e não um <img src> direto.
// Usada pelo rastro do navegador (painel Trabalho) e pelas entregas com captura.
import { useEffect, useState } from 'react';
import { buscarAutenticado } from '../../api/cliente';

export function ImagemAnexo({ anexoId, alt, className, carregando = 'Carregando imagem…', erro = 'Não foi possível carregar a imagem.' }: {
  anexoId: string; alt: string; className?: string; carregando?: string; erro?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [falhou, setFalhou] = useState(false);
  useEffect(() => {
    // anexo trocado = componente novo (quem usa põe key={anexoId}); o efeito só busca
    const ac = new AbortController(); let objeto: string | null = null;
    buscarAutenticado(`/v1/anexos/${anexoId}`, { signal: ac.signal }).then(r => r.blob()).then(b => { objeto = URL.createObjectURL(b); setUrl(objeto); }).catch(() => { if (!ac.signal.aborted) setFalhou(true); });
    return () => { ac.abort(); if (objeto) URL.revokeObjectURL(objeto); };
  }, [anexoId]);
  if (falhou) return <small className="wk-nav-erro">{erro}</small>;
  return url ? <img className={className} src={url} alt={alt} /> : <small className="shimmer">{carregando}</small>;
}

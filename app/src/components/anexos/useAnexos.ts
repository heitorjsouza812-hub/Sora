import { useCallback, useEffect, useRef, useState } from 'react';
import { prepararAnexos, revogarAnexo, type Anexo } from './tipos';

/** lista de anexos pendentes do composer, com erros de limite que somem sozinhos */
export function useAnexos() {
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [erro, setErro] = useState('');
  const atual = useRef(anexos);
  useEffect(() => { atual.current = anexos; }, [anexos]);

  useEffect(() => {
    if (!erro) return;
    const t = window.setTimeout(() => setErro(''), 6000);
    return () => window.clearTimeout(t);
  }, [erro]);

  // ao desmontar, revoga o que não foi enviado
  useEffect(() => () => atual.current.forEach(revogarAnexo), []);

  const adicionar = useCallback((arquivos: File[]) => {
    if (!arquivos.length) return;
    const { novos, erros } = prepararAnexos(arquivos, atual.current.length);
    if (novos.length) setAnexos(xs => { const r = [...xs, ...novos]; atual.current = r; return r; });
    setErro(erros.join(' '));
  }, []);

  const remover = useCallback((id: string) => {
    setAnexos(xs => {
      const alvo = xs.find(x => x.id === id);
      if (alvo) revogarAnexo(alvo);
      const r = xs.filter(x => x.id !== id);
      atual.current = r;
      return r;
    });
  }, []);

  /** esvazia sem revogar: os anexos foram com a mensagem */
  const entregar = useCallback(() => {
    const r = atual.current;
    atual.current = [];
    setAnexos([]);
    setErro('');
    return r;
  }, []);

  return { anexos, erro, adicionar, remover, entregar };
}

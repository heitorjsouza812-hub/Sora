import { useCallback, useEffect, useRef, useState } from 'react';

interface ApiDocumentPictureInPicture {
  requestWindow(opcoes: { width: number; height: number }): Promise<Window>;
}

type WindowComDocumentPiP = Window & { documentPictureInPicture?: ApiDocumentPictureInPicture };

function apiDisponivel(): ApiDocumentPictureInPicture | null {
  if (typeof window === 'undefined') return null;
  return (window as WindowComDocumentPiP).documentPictureInPicture ?? null;
}

function copiarFolhas(destino: Document) {
  document.querySelectorAll<HTMLLinkElement | HTMLStyleElement>('link[rel="stylesheet"], style')
    .forEach((folha) => destino.head.append(folha.cloneNode(true)));
}

export function useJanelaDestacada(): {
  suportado: boolean;
  aberta: boolean;
  abrir(): Promise<void>;
  fechar(): void;
  container: HTMLElement | null;
} {
  const suportado = !!apiDisponivel();
  const janela = useRef<Window | null>(null);
  const [container, setContainer] = useState<HTMLElement | null>(null);

  const aoFechar = useCallback(() => {
    janela.current = null;
    setContainer(null);
  }, []);

  const fechar = useCallback(() => {
    janela.current?.close();
    aoFechar();
  }, [aoFechar]);

  const abrir = useCallback(async () => {
    if (janela.current && !janela.current.closed) {
      janela.current.focus();
      return;
    }
    const api = apiDisponivel();
    if (!api) return;
    const pip = await api.requestWindow({ width: 420, height: 320 });
    pip.document.documentElement.lang = document.documentElement.lang || 'pt-BR';
    pip.document.title = 'Ilha da Sora';
    copiarFolhas(pip.document);
    pip.document.body.className = 'ilha-destacada';
    const raiz = pip.document.createElement('div');
    raiz.className = 'ilha-destacada__raiz';
    pip.document.body.append(raiz);
    janela.current = pip;
    setContainer(raiz);
    pip.addEventListener('pagehide', aoFechar, { once: true });
  }, [aoFechar]);

  useEffect(() => () => {
    janela.current?.removeEventListener('pagehide', aoFechar);
  }, [aoFechar]);

  return { suportado, aberta: !!container, abrir, fechar, container };
}

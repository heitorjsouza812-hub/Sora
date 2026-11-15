import { idFonte, urlPublica } from './fontes';
import type { FonteMensagem } from '../../state/projetos';
// Markdown das respostas (Sora e agentes): listas, negrito, itálico, links, tabelas e código.
// marked → HTML, DOMPurify sanitiza TUDO antes de ir para o DOM (nada de HTML cru sem limpar).
// Blocos de código ganham o botão "Copiar" (delegação de clique; toast "Copiado").
import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { markdownSeguro } from './markdownSeguro';
import { toast } from '../base';
import './markdown.css';

export interface MarkdownProps {
  texto: string;
  fontes?: FonteMensagem[];
  mensagemId?: string;
  /** mostra o cursor piscando no fim (resposta ainda sendo "digitada") */
  gerando?: boolean;
  className?: string;
}

export function Markdown({ texto, gerando = false, className = '', fontes, mensagemId }: MarkdownProps) {
  const raiz = useRef<HTMLDivElement>(null);
  const ultimo = useRef(texto);
  const renderizado = useRef(texto);
  const quadro = useRef<number | null>(null);
  const [html, setHtml] = useState(() => markdownSeguro(texto));
  useLayoutEffect(() => {
    ultimo.current = texto;
    if (texto === renderizado.current || quadro.current !== null) return;
    quadro.current = requestAnimationFrame(() => {
      quadro.current = null;
      renderizado.current = ultimo.current;
      setHtml(markdownSeguro(ultimo.current));
    });
  }, [texto]);
  useEffect(() => () => { if (quadro.current !== null) cancelAnimationFrame(quadro.current); quadro.current = null; }, []);
  useEffect(() => {
    const el = raiz.current;
    if (!el?.querySelector('.md-code')) return;
    let ativo = true;
    void import('./realcarCodigo').then(({ realcarCodigo }) => { if (ativo) realcarCodigo(el); }).catch(() => undefined);
    return () => { ativo = false; };
  }, [html]);
  useEffect(() => {
    const el = raiz.current;
    if (!el || !mensagemId || !fontes?.length) return;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nos: Text[] = [];
    while (walker.nextNode()) if (!walker.currentNode.parentElement?.closest('a, code, pre')) nos.push(walker.currentNode as Text);
    for (const no of nos) {
      const partes = no.textContent?.split(/(\[\d+\])/g) ?? [];
      if (partes.length < 2) continue;
      const frag = document.createDocumentFragment();
      for (const parte of partes) {
        const n = /^\[(\d+)\]$/.exec(parte)?.[1];
        const fonte = fontes.find(f => f.n === Number(n) && urlPublica(f.url));
        if (n && fonte) { const a = document.createElement('a'); a.href = '#' + idFonte(mensagemId, fonte.n); a.className = 'fonte-marca'; a.textContent = String(fonte.n); a.title = fonte.titulo; a.setAttribute('aria-label', `Fonte ${fonte.n}`); frag.append(a); }
        else frag.append(document.createTextNode(parte));
      }
      no.replaceWith(frag);
    }
  }, [html, fontes, mensagemId]);
  const copiarCodigo = (ev: MouseEvent<HTMLDivElement>) => {
    const botao = (ev.target as HTMLElement).closest('[data-copiar]');
    if (!botao) return;
    const codigo = botao.closest('.md-code')?.querySelector('code')?.textContent ?? '';
    void navigator.clipboard?.writeText(codigo).then(() => toast({ mensagem: 'Código copiado', tom: 'sucesso' }), () => toast({ mensagem: 'Não foi possível copiar', tom: 'erro' }));
  };
  return (
    // o HTML abaixo foi sanitizado pelo DOMPurify em markdownSeguro()
    <div ref={raiz} className={`md ${gerando ? 'is-gerando' : ''} ${className}`} onClick={copiarCodigo} dangerouslySetInnerHTML={{ __html: html }} />
  );
}

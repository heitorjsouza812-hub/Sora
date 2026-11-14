import type { FonteMensagem } from '../../state/projetos';

import { idFonte, urlPublica } from './fontes';

export function FontesMensagem({ mensagemId, fontes }: { mensagemId: string; fontes: FonteMensagem[] }) {
  return <nav className="msg-fontes" aria-label="Fontes da resposta">{fontes.filter(f => urlPublica(f.url)).map(f =>
    <a key={f.n} id={idFonte(mensagemId, f.n)} href={urlPublica(f.url)} target="_blank" rel="noopener noreferrer">
      <strong>[{f.n}] {f.titulo}</strong><small>{f.dominio}</small>
    </a>)}</nav>;
}

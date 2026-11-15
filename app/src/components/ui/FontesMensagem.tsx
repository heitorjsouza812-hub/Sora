import type { FonteMensagem } from '../../state/projetos';

import { idFonte, urlPublica } from './fontes';

/** Fontes da resposta: uma linha abaixo do texto, chips de 28 px com o número e o domínio (o título da página vai no title). */
export function FontesMensagem({ mensagemId, fontes }: { mensagemId: string; fontes: FonteMensagem[] }) {
  const publicas = fontes.filter(f => urlPublica(f.url));
  if (!publicas.length) return null;
  return <nav className="msg-fontes" aria-label="Fontes da resposta">
    <span className="msg-fontes-rotulo" aria-hidden="true">Fontes</span>
    {publicas.map(f =>
      <a key={f.n} id={idFonte(mensagemId, f.n)} href={urlPublica(f.url)} target="_blank" rel="noopener noreferrer" title={f.titulo}
        aria-label={`Fonte ${f.n}: ${f.titulo} (${f.dominio})`}>
        <b className="fonte-n" aria-hidden="true">{f.n}</b><span className="fonte-dominio">{f.dominio}</span>
      </a>)}
  </nav>;
}

// Chips de anexos: miniatura (imagens) ou ícone, nome, tamanho · tipo e, se editável, remover.
import { ehImagem, formatarTamanho, rotuloTipo, type Anexo } from './tipos';
import './anexos.css';

export interface ListaAnexosProps {
  anexos: Anexo[];
  /** sem onRemover a lista é só leitura (ex.: na bolha da mensagem) */
  onRemover?: (id: string) => void;
  className?: string;
}

function IconeArquivo() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>;
}

export function ListaAnexos({ anexos, onRemover, className = '' }: ListaAnexosProps) {
  if (!anexos.length) return null;
  return (
    <ul className={`anx-lista ${className}`} aria-label={`${anexos.length} ${anexos.length === 1 ? 'anexo' : 'anexos'}`}>
      {anexos.map(a => (
        <li key={a.id} className="anx-chip" data-imagem={ehImagem(a) || undefined}>
          <span className="anx-chip__previa" aria-hidden="true">
            {a.urlPrevia ? <img src={a.urlPrevia} alt="" /> : <IconeArquivo />}
          </span>
          <span className="anx-chip__texto">
            <strong title={a.nome}>{a.nome}</strong>
            <small>{formatarTamanho(a.tamanho)} · {rotuloTipo(a)}</small>
          </span>
          {onRemover && (
            <button type="button" className="anx-chip__remover" aria-label={`Remover ${a.nome}`} onClick={() => onRemover(a.id)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

// Input, Textarea e Select (nativo) com rótulo, ajuda e erro ligados por aria-describedby.
import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import './base.css';

interface Moldura {
  rotulo: string;
  /** texto de apoio abaixo do campo */
  ajuda?: ReactNode;
  /** mensagem de erro: marca aria-invalid e é anunciada */
  erro?: ReactNode;
  /** esconde o rótulo visualmente (continua para o leitor de tela) */
  rotuloOculto?: boolean;
}

function useCampo(id: string | undefined, { ajuda, erro }: Moldura, describedBy?: string) {
  const auto = useId();
  const campoId = id ?? `campo-${auto}`;
  const ajudaId = ajuda ? `${campoId}-ajuda` : undefined;
  const erroId = erro ? `${campoId}-erro` : undefined;
  return {
    campoId, ajudaId, erroId,
    aria: {
      'aria-invalid': erro ? true : undefined,
      'aria-describedby': [describedBy, ajudaId, erroId].filter(Boolean).join(' ') || undefined,
    },
  };
}

function Campo({ m, ids, children, className }: { m: Moldura; ids: ReturnType<typeof useCampo>; children: ReactNode; className?: string }) {
  return (
    <div className={['b-campo', m.erro ? 'is-erro' : '', className ?? ''].filter(Boolean).join(' ')}>
      <label htmlFor={ids.campoId} className={m.rotuloOculto ? 'b-sr' : 'b-campo__rotulo'}>{m.rotulo}</label>
      {children}
      {m.ajuda && <p id={ids.ajudaId} className="b-campo__ajuda">{m.ajuda}</p>}
      {m.erro && <p id={ids.erroId} className="b-campo__erro" role="alert">{m.erro}</p>}
    </div>
  );
}

export type InputProps = Moldura & InputHTMLAttributes<HTMLInputElement>;
export function Input({ rotulo, ajuda, erro, rotuloOculto, id, className, 'aria-describedby': db, ...resto }: InputProps) {
  const m = { rotulo, ajuda, erro, rotuloOculto };
  const ids = useCampo(id, m, db);
  return <Campo m={m} ids={ids} className={className}><input id={ids.campoId} className="b-input" {...ids.aria} {...resto} /></Campo>;
}

export type TextareaProps = Moldura & TextareaHTMLAttributes<HTMLTextAreaElement>;
export function Textarea({ rotulo, ajuda, erro, rotuloOculto, id, className, rows = 4, 'aria-describedby': db, ...resto }: TextareaProps) {
  const m = { rotulo, ajuda, erro, rotuloOculto };
  const ids = useCampo(id, m, db);
  return <Campo m={m} ids={ids} className={className}><textarea id={ids.campoId} rows={rows} className="b-input b-textarea" {...ids.aria} {...resto} /></Campo>;
}

export type SelectProps = Moldura & SelectHTMLAttributes<HTMLSelectElement> & {
  opcoes: { valor: string; rotulo: string; desativada?: boolean }[];
  /** primeira opção vazia (ex.: "Escolha…") */
  vazio?: string;
};
export function Select({ rotulo, ajuda, erro, rotuloOculto, id, className, opcoes, vazio, 'aria-describedby': db, ...resto }: SelectProps) {
  const m = { rotulo, ajuda, erro, rotuloOculto };
  const ids = useCampo(id, m, db);
  return (
    <Campo m={m} ids={ids} className={className}>
      <span className="b-select">
        <select id={ids.campoId} className="b-input" {...ids.aria} {...resto}>
          {vazio !== undefined && <option value="">{vazio}</option>}
          {opcoes.map((o) => <option key={o.valor} value={o.valor} disabled={o.desativada}>{o.rotulo}</option>)}
        </select>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
      </span>
    </Campo>
  );
}

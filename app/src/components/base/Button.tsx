// Button e IconButton únicos do app. "Carregando" = a Sora pensando (sem spinner).
import { cloneElement, isValidElement, type ButtonHTMLAttributes, type ReactElement, type ReactNode } from 'react';
import { SoraOrb } from '../mascot';
import './base.css';

export type Variante = 'primario' | 'secundario' | 'fantasma' | 'perigo';
export type Tamanho = 'P' | 'M' | 'G';

const ORB: Record<Tamanho, number> = { P: 16, M: 18, G: 22 };
// sobre o fundo claro do primário a Sora aparece em pontos escuros; nos demais, na cor dela
const corOrb = (v: Variante) => (v === 'primario' ? '#0B0D12' : '#E2ECFF');

interface Comum {
  variante?: Variante;
  tamanho?: Tamanho;
  /** a Sora pensa no lugar do ícone; o botão fica desativado e aria-busy */
  carregando?: boolean;
  iconeEsquerda?: ReactNode;
  iconeDireita?: ReactNode;
  /** ocupa a largura toda */
  bloco?: boolean;
}

export interface ButtonProps extends Comum, ButtonHTMLAttributes<HTMLButtonElement> {
  /** renderiza o filho único (ex.: <Link>) com o visual do botão */
  asChild?: boolean;
}

const classes = (variante: Variante, tamanho: Tamanho, bloco: boolean | undefined, extra?: string) =>
  ['b-btn', `b-btn--${variante}`, `b-btn--${tamanho}`, bloco ? 'b-btn--bloco' : '', extra ?? ''].filter(Boolean).join(' ');

function Conteudo({ carregando, iconeEsquerda, iconeDireita, tamanho, variante, children }: Comum & { tamanho: Tamanho; variante: Variante; children: ReactNode }) {
  return <>
    {carregando
      ? <span className="b-btn__icone" aria-hidden="true"><SoraOrb size={ORB[tamanho]} color={corOrb(variante)} state="thinking" glow={false} decorative /></span>
      : iconeEsquerda && <span className="b-btn__icone" aria-hidden="true">{iconeEsquerda}</span>}
    <span className="b-btn__rotulo">{children}</span>
    {iconeDireita && !carregando && <span className="b-btn__icone" aria-hidden="true">{iconeDireita}</span>}
  </>;
}

export function Button({
  variante = 'secundario', tamanho = 'M', carregando = false, iconeEsquerda, iconeDireita, bloco, asChild,
  className, children, disabled, type = 'button', ...resto
}: ButtonProps) {
  const cls = classes(variante, tamanho, bloco, className);
  if (asChild && isValidElement(children)) {
    const filho = children as ReactElement<{ className?: string; children?: ReactNode }>;
    return cloneElement(filho, {
      ...(resto as object),
      className: [cls, filho.props.className].filter(Boolean).join(' '),
      'aria-busy': carregando || undefined,
      'aria-disabled': disabled || carregando || undefined,
      children: <Conteudo {...{ carregando, iconeEsquerda, iconeDireita, tamanho, variante }}>{filho.props.children}</Conteudo>,
    } as object);
  }
  return (
    <button type={type} className={cls} disabled={disabled || carregando} aria-busy={carregando || undefined} {...resto}>
      <Conteudo {...{ carregando, iconeEsquerda, iconeDireita, tamanho, variante }}>{children}</Conteudo>
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'children'> {
  /** obrigatório: o botão só tem ícone */
  'aria-label': string;
  icone: ReactNode;
  variante?: Exclude<Variante, 'primario'> | 'primario';
  tamanho?: Tamanho;
  carregando?: boolean;
}

export function IconButton({ icone, variante = 'fantasma', tamanho = 'M', carregando = false, className, disabled, type = 'button', ...resto }: IconButtonProps) {
  return (
    <button type={type} className={['b-btn', 'b-icon', `b-btn--${variante}`, `b-btn--${tamanho}`, className ?? ''].filter(Boolean).join(' ')}
      disabled={disabled || carregando} aria-busy={carregando || undefined} {...resto}>
      <span className="b-btn__icone" aria-hidden="true">
        {carregando ? <SoraOrb size={ORB[tamanho]} color={corOrb(variante)} state="thinking" glow={false} decorative /> : icone}
      </span>
    </button>
  );
}

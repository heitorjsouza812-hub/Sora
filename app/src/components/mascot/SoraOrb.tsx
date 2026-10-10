// CONTRATO do mascote. Implementação: responsabilidade do agente "Prisma".
// As telas devem usar SÓ estas props — não depender de detalhes internos.
import type { Movimento } from '../../types';

export type OrbState =
  | 'arriving'      // pontos espalhados se juntam, olhos abrem (primeira abertura)
  | 'idle'          // respira, gira devagar, pisca
  | 'listening'     // superfície ondula, olhos olham para o campo de texto (lookAt)
  | 'thinking'      // THINKING ORB: Sora pensando/processando (substitui spinners)
  | 'coordinating'  // gira devagar (avatar na barra lateral)
  | 'working'       // agente trabalhando: usa o `movimento` próprio
  | 'done';         // calma, olhos abertos

export interface SoraOrbProps {
  size: number;                 // px (largura = altura do canvas)
  color?: string;               // padrão '#E2ECFF' (Sora); agentes passam sua cor
  state?: OrbState;             // padrão 'idle'
  movimento?: Movimento;        // padrão 'gira'
  lookAt?: { x: number; y: number } | null; // direção do olhar, -1..1
  pulseKey?: number;            // mudar o valor dispara um pulso de luz
  glow?: boolean;               // brilho no "chão" (padrão true quando size >= 96)
  className?: string;
  title?: string;               // aria-label
}

export function SoraOrb({ size, color = '#E2ECFF', className, title = 'Sora' }: SoraOrbProps) {
  // STUB provisório até o Prisma entregar o mascote de pontos.
  return (
    <div
      role="img"
      aria-label={title}
      className={className}
      style={{
        width: size, height: size, borderRadius: '50%',
        background: `radial-gradient(circle at 40% 40%, ${color}, transparent 70%)`,
        opacity: 0.6,
      }}
    />
  );
}

export default SoraOrb;

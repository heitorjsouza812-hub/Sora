// Área que aceita arquivos arrastados: mostra "Solte para anexar" e entrega os arquivos.
// Sem onArquivos, manda para o composer da tela (evento sora:anexar).
import { useRef, useState, type DragEvent, type ReactNode } from 'react';
import { enviarAoComposer } from './tipos';
import './anexos.css';

export interface ZonaSoltarProps {
  children: ReactNode;
  onArquivos?: (arquivos: File[]) => void;
  className?: string;
  desativada?: boolean;
}

const temArquivos = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files');

export function ZonaSoltar({ children, onArquivos = enviarAoComposer, className = '', desativada = false }: ZonaSoltarProps) {
  const [sobre, setSobre] = useState(false);
  const profundidade = useRef(0);
  const sair = () => { profundidade.current = 0; setSobre(false); };
  return (
    <div
      className={`anx-zona ${className}`}
      data-sobre={sobre || undefined}
      onDragEnter={(e) => { if (desativada || !temArquivos(e)) return; e.preventDefault(); profundidade.current++; setSobre(true); }}
      onDragOver={(e) => { if (desativada || !temArquivos(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
      onDragLeave={() => { if (--profundidade.current <= 0) sair(); }}
      onDrop={(e) => {
        if (desativada || !temArquivos(e)) return;
        e.preventDefault();
        e.stopPropagation();
        sair();
        onArquivos(Array.from(e.dataTransfer.files));
      }}
    >
      {children}
      {sobre && (
        <div className="anx-zona__aviso" aria-hidden="true">
          <span><svg viewBox="0 0 24 24"><path d="M12 16V4M6 10l6-6 6 6M5 20h14" /></svg>Solte para anexar</span>
        </div>
      )}
    </div>
  );
}

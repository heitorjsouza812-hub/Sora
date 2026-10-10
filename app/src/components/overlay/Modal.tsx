import { useId, useRef, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { useDialogA11y } from './useDialogA11y';
import './overlay.css';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  closeOnBackdrop?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
  className?: string;
}

export function Modal({
  open, onClose, title, description, children, footer,
  size = 'md', closeOnBackdrop = true, initialFocusRef, className = '',
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialogA11y(open, onClose, dialogRef, initialFocusRef);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="sora-overlay-backdrop"
      onPointerDown={(event) => {
        if (closeOnBackdrop && event.currentTarget === event.target) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className={`sora-modal ${className}`}
        data-size={size}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <header className="sora-modal__header">
          <div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div>
          <button className="sora-overlay-close" type="button" onClick={onClose} aria-label="Fechar"><span aria-hidden="true">×</span></button>
        </header>
        <div className="sora-modal__body">{children}</div>
        {footer && <footer className="sora-modal__footer">{footer}</footer>}
      </section>
    </div>,
    document.body,
  );
}


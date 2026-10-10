import { useId, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useDialogA11y } from './useDialogA11y';
import './overlay.css';

export interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  closeOnBackdrop?: boolean;
  className?: string;
}

export function BottomSheet({
  open, onClose, title, description, children, footer, closeOnBackdrop = true, className = '',
}: BottomSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const dragRef = useRef({ startY: 0, startedAt: 0 });
  const [drag, setDrag] = useState(0);
  const [dragging, setDragging] = useState(false);
  const titleId = useId();
  const descriptionId = useId();
  useDialogA11y(open, onClose, sheetRef);

  if (!open || typeof document === 'undefined') return null;

  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.isPrimary) return;
    dragRef.current = { startY: event.clientY, startedAt: performance.now() };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    setDrag(Math.max(0, event.clientY - dragRef.current.startY));
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    const distance = Math.max(0, event.clientY - dragRef.current.startY);
    const elapsed = Math.max(1, performance.now() - dragRef.current.startedAt);
    const velocity = distance / elapsed;
    setDragging(false);
    if (distance > 96 || velocity > .65) {
      setDrag(0);
      onClose();
    } else {
      setDrag(0);
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return createPortal(
    <div
      className="sora-overlay-backdrop sora-sheet-backdrop"
      onPointerDown={(event) => {
        if (closeOnBackdrop && event.currentTarget === event.target) onClose();
      }}
    >
      <section
        ref={sheetRef}
        className={`sora-sheet ${className}`}
        style={{ '--sheet-drag': `${drag}px` } as CSSProperties}
        data-dragging={dragging}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <div
          className="sora-sheet__handle-zone"
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          aria-hidden="true"
        ><span className="sora-sheet__handle" /></div>
        <header className="sora-sheet__header">
          <div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div>
          <button className="sora-overlay-close" type="button" onClick={onClose} aria-label="Fechar"><span aria-hidden="true">×</span></button>
        </header>
        <div className="sora-sheet__body">{children}</div>
        {footer && <footer className="sora-sheet__footer">{footer}</footer>}
      </section>
    </div>,
    document.body,
  );
}


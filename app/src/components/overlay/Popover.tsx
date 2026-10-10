import { useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import './overlay.css';

export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  align?: 'start' | 'center' | 'end';
  side?: 'top' | 'bottom';
  width?: number;
  role?: 'dialog' | 'menu';
  ariaLabel?: string;
  className?: string;
}

export function Popover({
  open, onClose, anchorRef, children, align = 'end', side = 'bottom',
  width = 300, role = 'dialog', ariaLabel, className = '',
}: PopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const anchor = anchorRef.current;
      const popover = popoverRef.current;
      if (!anchor || !popover) return;
      const a = anchor.getBoundingClientRect();
      const p = popover.getBoundingClientRect();
      const gap = 8;
      const desiredLeft = align === 'start' ? a.left : align === 'center' ? a.left + (a.width - p.width) / 2 : a.right - p.width;
      const left = Math.max(12, Math.min(window.innerWidth - p.width - 12, desiredLeft));
      const preferredTop = side === 'top' ? a.top - p.height - gap : a.bottom + gap;
      const fallbackTop = side === 'top' ? a.bottom + gap : a.top - p.height - gap;
      const top = preferredTop >= 12 && preferredTop + p.height <= window.innerHeight - 12 ? preferredTop : Math.max(12, fallbackTop);
      popover.style.top = `${top}px`;
      popover.style.left = `${left}px`;
      popover.style.width = `${width}px`;
    };
    const frame = window.requestAnimationFrame(update);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [align, anchorRef, open, side, width]);

  useLayoutEffect(() => {
    if (!open) return;
    const onPointerDown = (event: globalThis.PointerEvent) => {
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !anchorRef.current?.contains(target)) onCloseRef.current();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        anchorRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [anchorRef, open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={popoverRef}
      className={`sora-popover ${className}`}
      role={role}
      aria-label={ariaLabel}
    >
      {children}
    </div>,
    document.body,
  );
}


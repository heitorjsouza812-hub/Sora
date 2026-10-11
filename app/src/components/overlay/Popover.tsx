import { useEffect, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { empilharCamada } from './camadas';
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
    // Esc fecha só a camada do topo (um Popover dentro de um Modal não fecha o Modal)
    const camada = popoverRef.current ? empilharCamada(popoverRef.current, {
      modal: false,
      onEsc: () => { onCloseRef.current(); anchorRef.current?.focus(); },
    }) : null;
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      camada?.remover();
    };
  }, [anchorRef, open]);

  // menus: foco no 1º item ao abrir (se o dono ainda não focou nenhum)
  useEffect(() => {
    if (!open || role !== 'menu') return;
    const frame = window.requestAnimationFrame(() => {
      const menu = popoverRef.current;
      if (menu && !menu.contains(document.activeElement)) menu.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, role]);

  // menus: setas circulam, Home/End vão às pontas (quem já trata as teclas chama preventDefault)
  const teclaMenu = (event: KeyboardEvent<HTMLDivElement>) => {
    if (role !== 'menu' || event.defaultPrevented) return;
    const itens = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])'));
    if (!itens.length) return;
    const atual = itens.indexOf(document.activeElement as HTMLElement);
    const n = itens.length;
    const destino = event.key === 'ArrowDown' ? (atual + 1) % n : event.key === 'ArrowUp' ? (atual - 1 + n) % n
      : event.key === 'Home' ? 0 : event.key === 'End' ? n - 1 : -1;
    if (destino < 0) return;
    event.preventDefault();
    itens[destino].focus();
  };

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={popoverRef}
      className={`sora-popover ${className}`}
      role={role}
      aria-label={ariaLabel}
      onKeyDown={teclaMenu}
    >
      {children}
    </div>,
    document.body,
  );
}


import type { RefObject } from 'react';
import { Popover } from '../overlay/Popover';
import './review.css';

export type AccountAction = 'configuracoes' | 'plugins' | 'sair';

export interface AccountMenuProps {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  empresa: string;
  plano: string;
  onSelect: (action: AccountAction) => void;
}

export function AccountMenu({ open, onClose, anchorRef, empresa, plano, onSelect }: AccountMenuProps) {
  const select = (action: AccountAction) => {
    onSelect(action);
    onClose();
  };
  return (
    <Popover open={open} onClose={onClose} anchorRef={anchorRef} ariaLabel="Menu da conta" role="menu" className="account-popover" width={260}>
      <div className="account-popover__identity"><strong>{empresa}</strong><span>{plano}</span></div>
      <div className="account-popover__actions">
        <button role="menuitem" type="button" onClick={() => select('configuracoes')}>Configurações</button>
        <button role="menuitem" type="button" onClick={() => select('plugins')}>Plugins</button>
        <button role="menuitem" type="button" onClick={() => select('sair')}>Sair</button>
      </div>
    </Popover>
  );
}


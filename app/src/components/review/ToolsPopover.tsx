import type { RefObject } from 'react';
import { Link } from 'react-router-dom';
import { PLUGIN_ICONS } from '../../data/pluginIcons';
import { PluginMark } from '../ui/PluginMark';
import { Popover } from '../overlay/Popover';
import './review.css';

export interface ToolsPopoverProps {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  plugins: string[];
  onManage?: () => void;
}

export function ToolsPopover({ open, onClose, anchorRef, plugins, onManage }: ToolsPopoverProps) {
  return (
    <Popover open={open} onClose={onClose} anchorRef={anchorRef} ariaLabel="Plugins conectados" role="dialog" className="tools-popover" width={320}>
      <p className="review-popover-title">Plugins conectados</p>
      <div className="tools-popover__list" role="list">
        {plugins.map((nome) => {
          const icon = PLUGIN_ICONS.find((item) => item.name === nome);
          return <div className="tools-popover__item" role="listitem" key={nome}>
            <PluginMark nome={nome} cor={icon?.hex ?? '#E2ECFF'} path={icon?.path ?? null} size={26} />
            <strong>{nome}</strong>
            <small>● Conectado</small>
          </div>;
        })}
        {!plugins.length && <div className="review-empty">Nenhum plugin conectado.</div>}
      </div>
      <Link className="tools-popover__footer" to="/plugins" onClick={() => { onManage?.(); onClose(); }}>Gerenciar plugins</Link>
    </Popover>
  );
}


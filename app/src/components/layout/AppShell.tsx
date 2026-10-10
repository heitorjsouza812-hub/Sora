import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <section className="app-stage">
        <header className="topbar"><span>{title}</span></header>
        {children}
      </section>
    </div>
  );
}


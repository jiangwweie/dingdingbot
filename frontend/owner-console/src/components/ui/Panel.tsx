import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  title?: ReactNode;
}

export function Panel({ children, title }: PanelProps) {
  return (
    <section className="panel">
      {title ? <div className="panel__header">{title}</div> : null}
      <div className="panel__body">{children}</div>
    </section>
  );
}

import type { ReactNode } from "react";

interface PageHeaderProps {
  actions?: ReactNode;
  description?: ReactNode;
  title: string;
}

export function PageHeader({ actions, description, title }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-header__title">{title}</h1>
        {description ? <div className="page-header__description">{description}</div> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

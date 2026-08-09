interface UnavailablePanelProps {
  detail: string;
  title: string;
}

export function UnavailablePanel({ detail, title }: UnavailablePanelProps) {
  return (
    <section className="panel unavailable-panel" role="status">
      <strong>{title}</strong>
      <span>{detail}</span>
    </section>
  );
}

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, LoaderCircle } from "lucide-react";

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">CULTIVATINATOR / WORKSPACE</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <span className="badge">Culture Library · Milestone 2A</span>
    </header>
  );
}
export function Panel({
  title,
  icon: Icon,
  children,
  className = "",
  label,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <h2>
          <Icon size={17} aria-hidden="true" />
          {title}
        </h2>
        {label && <span className="panel-label">{label}</span>}
      </div>
      {children}
    </section>
  );
}
export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon size={26} strokeWidth={1.4} aria-hidden="true" />
      </span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
    </div>
  );
}
export function LoadingState() {
  return (
    <div role="status" className="feedback">
      <LoaderCircle size={20} aria-hidden="true" />
      Connecting to the application…
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: string;
  retry: () => void;
}) {
  return (
    <div role="alert" className="feedback error">
      <AlertTriangle size={24} aria-hidden="true" />
      <div>
        <h2>Unable to connect to Cultivatinator</h2>
        <p>Check that the application is running, then try again. {error}</p>
      </div>
      <button onClick={retry}>Retry connection</button>
    </div>
  );
}

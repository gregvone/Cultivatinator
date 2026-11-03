import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

// Native details keeps children mounted, including forms and pending upload queues.
export default function CollapsiblePanel({
  title,
  summary,
  children,
  defaultOpen = false,
  className = "",
  level = 2,
  revealWhen = false,
  onExpand,
}: {
  title: ReactNode;
  summary?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  level?: 2 | 3 | 4;
  revealWhen?: boolean;
  onExpand?: () => void;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const element = useRef<HTMLDetailsElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const id = useId();
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  function reveal() {
    if (element.current) element.current.open = true;
    setExpanded(true);
  }
  useEffect(() => {
    if (revealWhen) reveal();
  }, [revealWhen]);
  useEffect(() => {
    const content = body.current!;
    const revealErrors = () => {
      if (content.querySelector('[aria-invalid="true"], [role="alert"]'))
        reveal();
    };
    revealErrors();
    const observer = new MutationObserver(revealErrors);
    observer.observe(content, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["aria-invalid", "role"],
    });
    return () => observer.disconnect();
  }, []);
  return (
    <section className="collapse-section">
      <details
        ref={element}
        open={expanded}
        className={`panel collapsible-panel ${className}`}
        onToggle={(e) => {
          // Nested details toggle independently.
          if (e.target !== e.currentTarget) return;
          setExpanded(e.currentTarget.open);
          if (e.currentTarget.open) onExpand?.();
        }}
        onInvalidCapture={() => reveal()}
      >
        <summary role="button" aria-expanded={expanded} aria-controls={id}>
          <div className="collapse-heading">
            <Heading>{title}</Heading>
            {summary && <span className="collapse-summary">{summary}</span>}
          </div>
          <ChevronDown
            size={20}
            className="collapse-chevron"
            aria-hidden="true"
          />
        </summary>
        <div id={id} ref={body} className="collapse-body">
          {children}
        </div>
      </details>
    </section>
  );
}

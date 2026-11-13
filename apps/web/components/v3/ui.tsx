import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Tone = "neutral" | "ok" | "warn" | "bad" | "info";

const TONE: Record<Tone, string> = {
  neutral: "bg-[var(--subtle)] text-[var(--foreground)] border-[var(--border)]",
  ok: "bg-[var(--ok-bg)] text-[var(--ok)] border-[var(--ok-border)]",
  warn: "bg-[var(--warn-bg)] text-[var(--warn)] border-[var(--warn-border)]",
  bad: "bg-[var(--bad-bg)] text-[var(--bad)] border-[var(--bad-border)]",
  info: "bg-[var(--info-bg)] text-[var(--info)] border-[var(--info-border)]",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-xs font-medium ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone }: { tone: Tone }) {
  const color = { neutral: "#a1a1aa", ok: "var(--ok)", warn: "#ca8a04", bad: "var(--bad)", info: "var(--info)" }[tone];
  return <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: color }} />;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" };

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const styles = {
    primary: "bg-[var(--primary)] text-white hover:bg-[var(--primary-hover)] border-transparent",
    secondary: "bg-[var(--surface)] text-[var(--foreground)] hover:bg-[var(--subtle)] border-[var(--border-strong)]",
    ghost: "bg-transparent text-[var(--foreground)] hover:bg-[var(--subtle)] border-transparent",
    danger: "bg-[var(--surface)] text-[var(--bad)] hover:bg-[var(--bad-bg)] border-[var(--bad-border)]",
  }[variant];
  return (
    <button
      {...props}
      className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md border px-3 text-sm font-medium shadow-[0_1px_1px_rgba(0,0,0,0.04)] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  );
}

export function Panel({ title, actions, children, className = "", padded = true }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`rounded-lg border border-[var(--border)] bg-[var(--surface)] ${className}`}>
      {title || actions ? (
        <header className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-2.5">
          <h3 className="text-sm font-semibold">{title}</h3>
          {actions}
        </header>
      ) : null}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-[var(--muted-foreground)]">{description}</p> : null}
      </div>
      {actions ? <div className="flex gap-2">{actions}</div> : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border-strong)] px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mt-1 text-sm text-[var(--muted-foreground)]">{children}</div> : null}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return <div className={`rounded-md border px-3 py-2 text-sm ${TONE[tone]}`}>{children}</div>;
}

export function Spinner() {
  return (
    <span
      aria-label="Loading"
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--border-strong)] border-t-[var(--foreground)]"
    />
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="font-mono text-xs text-[var(--muted-foreground)]">{children}</code>;
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href as never} className="font-medium underline decoration-[var(--border-strong)] underline-offset-2 hover:decoration-[var(--foreground)]">
      {children}
    </Link>
  );
}

export const inputClass =
  "w-full rounded-md border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-1.5 text-sm placeholder:text-[var(--muted-foreground)] focus:border-[var(--ring)] focus:outline-none";

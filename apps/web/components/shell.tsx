import Link from "next/link";
import { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border)] bg-[rgba(255,253,248,0.86)] backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-[var(--warm)]">Trace</p>
            <h1 className="text-xl font-semibold text-[var(--foreground)]">
              Trace - Sovereign Discovery Copilot
            </h1>
          </div>
          <nav className="flex gap-5 text-sm text-[var(--accent)]">
            <Link href="/matters">Matters</Link>
            <Link href="/matters/new">New Matter</Link>
            <Link href="/matters/demo/ask">Ask</Link>
            <Link href="/matters/demo/settings">Settings</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}

export function PageCard({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-[var(--border)] bg-[var(--panel)] p-6 shadow-[0_10px_30px_rgba(29,29,26,0.06)]">
      {eyebrow ? (
        <p className="mb-2 text-xs uppercase tracking-[0.24em] text-[var(--warm)]">{eyebrow}</p>
      ) : null}
      <h2 className="mb-4 text-2xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

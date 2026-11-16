"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

type Matter = { id: string; name: string; matter_code?: string | null };

const PRIMARY = [
  { slug: "investigate", label: "Investigate" },
  { slug: "review", label: "Review" },
  { slug: "changes", label: "Changes" },
  { slug: "sources", label: "Sources" },
  { slug: "packets", label: "Packets" },
];

const MORE = [
  { slug: "search", label: "Search" },
  { slug: "ask", label: "Q&A (legacy)" },
  { slug: "chronology", label: "Chronology" },
  { slug: "entities", label: "Entities" },
  { slug: "contradictions", label: "Contradictions" },
  { slug: "memo", label: "Issue memo" },
  { slug: "documents", label: "Document viewer" },
  { slug: "settings", label: "Settings" },
];

export function TopBar({ children }: { children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--background)]/95 backdrop-blur">
      <div className="flex h-12 items-center gap-3 px-4">
        <Link href="/matters" className="flex items-center gap-2 font-serif text-[17px] tracking-[-0.01em]">
          <Logo />
          Trace
        </Link>
        {children}
        <div className="ml-auto flex items-center gap-4 text-[13px] text-[var(--muted-foreground)]">
          <Link href="/matters" className="hover:text-[var(--foreground)]">Matters</Link>
          <button
            type="button"
            className="hover:text-[var(--foreground)]"
            onClick={() => fetch("/api/auth/logout", { method: "POST" }).finally(() => window.location.assign("/sign-in"))}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

export function Logo() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <circle cx="8" cy="8" r="7.25" fill="none" stroke="var(--primary)" strokeWidth="1.5" />
      <circle cx="8" cy="8" r="2.5" fill="var(--primary)" />
    </svg>
  );
}

export function MatterShell({ matterId, children }: { matterId: string; children: ReactNode }) {
  const pathname = usePathname();
  const [matter, setMatter] = useState<Matter | null>(null);
  const [changes, setChanges] = useState<number | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    fetch(`/api/matters/${matterId}`, { cache: "no-store" })
      .then((r) => {
        if (r.status === 401) window.location.assign("/sign-in");
        return r.ok ? r.json() : null;
      })
      .then(setMatter)
      .catch(() => setMatter(null));
    fetch(`/api/v3/matters/${matterId}/changes`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: unknown[]) => setChanges(rows.length))
      .catch(() => setChanges(null));
  }, [matterId, pathname]);

  const active = pathname.split("/")[3] ?? "investigate";
  const activeSlug = active === "claims" ? "review" : active;
  useEffect(() => {
    if (MORE.some((m) => m.slug === activeSlug)) setMoreOpen(true);
  }, [activeSlug]);

  return (
    <div className="min-h-screen">
      <TopBar>
        <span className="text-[var(--border-strong)]">/</span>
        <span className="truncate text-[13px] font-medium">{matter?.name ?? "Matter"}</span>
        {matter?.matter_code ? <span className="font-mono text-[11px] text-[var(--muted-foreground)]">{matter.matter_code}</span> : null}
      </TopBar>
      <div className="flex">
        <nav className="sticky top-12 hidden h-[calc(100vh-3rem)] w-48 shrink-0 border-r border-[var(--border)] px-3 py-5 md:block">
          <ul className="space-y-0.5">
            {PRIMARY.map((item) => (
              <li key={item.slug}>
                <NavLink href={`/matters/${matterId}/${item.slug}`} active={activeSlug === item.slug}>
                  {item.label}
                  {item.slug === "changes" && changes ? (
                    <span className="ml-auto font-mono text-[11px] text-[var(--warn)]">{changes}</span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setMoreOpen((open) => !open)}
            className="label-caps mt-6 flex w-full items-center justify-between px-2.5 hover:text-[var(--foreground)]"
            aria-expanded={moreOpen}
          >
            More tools
            <span aria-hidden>{moreOpen ? "−" : "+"}</span>
          </button>
          {moreOpen ? (
            <ul className="mt-1 space-y-0.5">
              {MORE.map((item) => (
                <li key={item.slug}>
                  <NavLink href={`/matters/${matterId}/${item.slug}`} active={activeSlug === item.slug} subtle>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          ) : null}
        </nav>
        <main className="min-w-0 flex-1 px-6 py-8 lg:px-12">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

function NavLink({ href, active, subtle, children }: { href: string; active: boolean; subtle?: boolean; children: ReactNode }) {
  return (
    <Link
      href={href as never}
      className={`-ml-px flex items-center gap-2 border-l-2 px-2.5 py-1.5 text-[13px] ${
        active
          ? "border-[var(--primary)] font-medium text-[var(--foreground)]"
          : `border-transparent ${subtle ? "text-[var(--muted-foreground)]" : "text-[#4a4741]"} hover:text-[var(--foreground)]`
      }`}
    >
      {children}
    </Link>
  );
}

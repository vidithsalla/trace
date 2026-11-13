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
    <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="flex h-12 items-center gap-3 px-4">
        <Link href="/matters" className="flex items-center gap-2 text-sm font-semibold">
          <Logo />
          Trace
        </Link>
        {children}
        <div className="ml-auto flex items-center gap-3 text-sm text-[var(--muted-foreground)]">
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
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
      <rect x="0.5" y="0.5" width="17" height="17" rx="4" fill="var(--primary)" />
      <path d="M5 5.5h8M9 5.5v7.5" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
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
        <span className="truncate text-sm font-medium">{matter?.name ?? "Matter"}</span>
        {matter?.matter_code ? <span className="font-mono text-xs text-[var(--muted-foreground)]">{matter.matter_code}</span> : null}
      </TopBar>
      <div className="flex">
        <nav className="sticky top-12 hidden h-[calc(100vh-3rem)] w-52 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] px-2 py-3 md:block">
          <ul className="space-y-0.5">
            {PRIMARY.map((item) => (
              <li key={item.slug}>
                <NavLink href={`/matters/${matterId}/${item.slug}`} active={activeSlug === item.slug}>
                  {item.label}
                  {item.slug === "changes" && changes ? (
                    <span className="ml-auto rounded bg-[var(--warn-bg)] px-1.5 text-xs font-medium text-[var(--warn)]">{changes}</span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setMoreOpen((open) => !open)}
            className="mt-5 flex w-full items-center justify-between px-2 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
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
        <main className="min-w-0 flex-1 px-6 py-6 lg:px-10">
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
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-sm ${
        active
          ? "bg-[var(--subtle)] font-medium text-[var(--foreground)]"
          : `${subtle ? "text-[var(--muted-foreground)]" : "text-[var(--foreground)]"} hover:bg-[var(--subtle)]`
      }`}
    >
      {children}
    </Link>
  );
}

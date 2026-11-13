"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { MatterShell, TopBar } from "@/components/v3/matter-shell";

const MATTER_PATH = /^\/matters\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const match = pathname.match(MATTER_PATH);
  if (match) {
    return <MatterShell matterId={match[1]}>{children}</MatterShell>;
  }
  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}

export function PageCard({ title, eyebrow, children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-5">
        {eyebrow ? <p className="text-xs font-medium text-[var(--muted-foreground)]">{eyebrow}</p> : null}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">{children}</div>
    </section>
  );
}

import Link from "next/link";
import type { Route } from "next";

import { AppShell, PageCard } from "@/components/shell";
import { workflowCards } from "@/lib/demo-data";

export default function HomePage() {
  return (
    <AppShell>
      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <PageCard eyebrow="Private Legal AI" title="Trace keeps discovery review grounded in your evidence.">
          <p className="max-w-2xl text-base leading-7 text-neutral-700">
            Upload a matter, inspect ingestion, search the record, ask grounded questions, and
            generate chronologies, witness summaries, contradiction reports, and first-pass issue
            memos without leaving your environment.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              className="rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-medium text-white"
              href="/matters"
            >
              Open Matters
            </Link>
            <Link
              className="rounded-full border border-[var(--border)] px-5 py-3 text-sm font-medium"
              href="/sign-in"
            >
              Sign In
            </Link>
          </div>
        </PageCard>
        <PageCard eyebrow="Build State" title="MVP foundation">
          <ul className="space-y-3 text-sm text-neutral-700">
            <li>FastAPI API with Trace-branded auth, matter, document, search, and workflow routes.</li>
            <li>Dramatiq worker pipeline for ingestion and export jobs.</li>
            <li>Seeded Acme matter and truth-map eval coverage.</li>
            <li>Next.js shell for ask, chronology, entities, memo, and settings workflows.</li>
          </ul>
        </PageCard>
      </div>

      <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {workflowCards.map((card) => (
          <Link
            key={card.title}
            href={card.href as Route}
            className="rounded-3xl border border-[var(--border)] bg-[rgba(255,253,248,0.82)] p-5 shadow-[0_8px_24px_rgba(29,29,26,0.05)] transition hover:-translate-y-1"
          >
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--warm)]">Workflow</p>
            <h3 className="mt-2 text-xl font-semibold">{card.title}</h3>
            <p className="mt-3 text-sm leading-6 text-neutral-700">{card.description}</p>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}

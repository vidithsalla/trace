import Link from "next/link";

import { Logo } from "@/components/v3/matter-shell";

const LAYERS = [
  {
    title: "Source integrity",
    body: "A deterministic check that every quoted passage exists, unchanged, in the exact document version and matter it claims to come from.",
    tag: "Verified by code",
  },
  {
    title: "Support suggestion",
    body: "A model reads the passages, including ones found by a separate search for opposing evidence, and suggests whether they support, qualify or contradict the claim.",
    tag: "Suggested by a model",
  },
  {
    title: "Human decision",
    body: "A reviewer accepts, rejects or leaves the claim unresolved. The decision is tied to that claim revision and that exact evidence set.",
    tag: "Recorded for a person",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <header className="border-b border-[var(--border)]">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <span className="flex items-center gap-2 text-sm font-semibold"><Logo /> Trace</span>
          <nav className="flex items-center gap-5 text-sm text-[var(--muted-foreground)]">
            <a className="hover:text-[var(--foreground)]" href="https://github.com/vidithsalla/trace">GitHub</a>
            <Link className="inline-flex h-8 items-center rounded-md bg-[var(--primary)] px-3 font-medium text-white hover:bg-[var(--primary-hover)]" href="/sign-in">
              Open the demo
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6">
        <section className="py-20">
          <p className="text-sm font-medium text-[var(--muted-foreground)]">Evidence review for document-heavy disputes</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight">
            Know which version of which document a finding rests on, and when that stops being true.
          </h1>
          <p className="mt-5 max-w-2xl text-base text-[var(--muted-foreground)]">
            Trace proposes claims from your documents, shows the passages for and against each one,
            and records a reviewer&apos;s decision against the exact sources they saw. When a source is
            corrected, the old approval is kept in history and flagged, so it never passes for a current one.
          </p>
          <div className="mt-8 flex gap-3">
            <Link className="inline-flex h-9 items-center rounded-md bg-[var(--primary)] px-4 text-sm font-medium text-white hover:bg-[var(--primary-hover)]" href="/sign-in">
              Open the demo
            </Link>
            <a className="inline-flex h-9 items-center rounded-md border border-[var(--border-strong)] px-4 text-sm font-medium hover:bg-[var(--subtle)]" href="https://github.com/vidithsalla/trace#install">
              Install locally
            </a>
          </div>
        </section>

        <section className="border-t border-[var(--border)] py-14">
          <h2 className="text-lg font-semibold">Three separate questions, never merged into one score</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {LAYERS.map((layer, i) => (
              <div key={layer.title} className="rounded-lg border border-[var(--border)] p-5">
                <p className="font-mono text-xs text-[var(--muted-foreground)]">{i + 1}</p>
                <h3 className="mt-2 font-semibold">{layer.title}</h3>
                <p className="mt-2 text-sm text-[var(--muted-foreground)]">{layer.body}</p>
                <p className="mt-4 text-xs font-medium">{layer.tag}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-10 border-t border-[var(--border)] py-14 md:grid-cols-2">
          <div>
            <h2 className="text-lg font-semibold">A real quote can still be the wrong answer</h2>
            <p className="mt-3 text-sm text-[var(--muted-foreground)]">
              &ldquo;Invoice 7A is approved for payment subject to verification of delivery receipts&rdquo; is a
              genuine quote. It does not support &ldquo;invoice 7A was approved unconditionally.&rdquo; Trace shows the
              quote as verified and the claim as qualified, and surfaces the later email asking to hold
              payment, so the reviewer sees all of it before deciding.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold">Your documents stay on your machine</h2>
            <p className="mt-3 text-sm text-[var(--muted-foreground)]">
              The default setup runs a local model through Ollama. A hosted model is an explicit opt-in that
              refuses to start until you acknowledge that passages will leave the machine.
            </p>
            <pre className="mt-4 overflow-x-auto rounded-md border border-[var(--border)] bg-[var(--subtle)] p-3 font-mono text-xs">
{`git clone https://github.com/vidithsalla/trace
cd trace && ./install.sh`}
            </pre>
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--border)]">
        <div className="mx-auto max-w-5xl px-6 py-6 text-xs text-[var(--muted-foreground)]">
          Open-source portfolio project. Synthetic demo data. Not legal advice, and not validated by attorneys.
        </div>
      </footer>
    </div>
  );
}

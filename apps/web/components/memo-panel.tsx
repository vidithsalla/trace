"use client";

import { FormEvent, useState } from "react";

type Citation = {
  id: string | null;
  document_id: string;
  document_name: string;
  page: number | null;
  chunk_id: string | null;
  quote: string;
  viewer_url: string | null;
  validation_status: string | null;
};

type MemoFact = {
  statement: string;
  citation_ids: string[];
  citations: Citation[];
};

type MemoContent = {
  issue: string;
  answer_in_brief: string;
  supporting_facts: MemoFact[];
  contrary_facts: MemoFact[];
  gaps: string[];
  next_documents_to_review: string[];
};

type MemoRead = {
  id: string;
  matter_id: string;
  title: string;
  status: string;
  source_run_id: string | null;
  content_json: MemoContent;
  content_markdown: string | null;
};

const EXAMPLE_ISSUES = [
  "Whether Acme gave timely notice of the delivery problem",
  "Whether payment approval authority was final or conditional",
];

export function MemoPanel({ matterId }: { matterId: string }) {
  const [issue, setIssue] = useState(EXAMPLE_ISSUES[0]);
  const [memo, setMemo] = useState<MemoRead | null>(null);
  const [editableContent, setEditableContent] = useState<MemoContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  async function generateMemo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!issue.trim()) {
      return;
    }
    setError(null);
    setIsGenerating(true);
    const response = await fetch(`/api/matters/${matterId}/memos`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ issue, limit: 12 }),
    });
    setIsGenerating(false);
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Trace could not generate this issue memo.");
      return;
    }
    const body = (await response.json()) as MemoRead;
    setMemo(body);
    setEditableContent(body.content_json);
  }

  async function saveMemo() {
    if (!memo || !editableContent) {
      return;
    }
    setIsSaving(true);
    setError(null);
    const response = await fetch(`/api/memos/${memo.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        title: editableContent.issue,
        status: "draft",
        content_json: editableContent,
      }),
    });
    setIsSaving(false);
    if (!response.ok) {
      setError("Trace could not save the memo edit.");
      return;
    }
    const body = (await response.json()) as MemoRead;
    setMemo(body);
    setEditableContent(body.content_json);
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
      <section className="space-y-5">
        <form onSubmit={generateMemo} className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
            Citation-backed draft
          </p>
          <h3 className="mt-2 text-xl font-semibold">Generate an issue memo</h3>
          <textarea
            className="mt-4 min-h-28 w-full rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm leading-6 outline-none focus:border-[var(--accent)]"
            value={issue}
            onChange={(event) => setIssue(event.target.value)}
          />
          <div className="mt-4 flex flex-wrap gap-2">
            {EXAMPLE_ISSUES.map((item) => (
              <button
                key={item}
                className="rounded-full border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--accent)]"
                type="button"
                onClick={() => setIssue(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <button
            className="mt-5 rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
            disabled={isGenerating || !issue.trim()}
            type="submit"
          >
            {isGenerating ? "Drafting..." : "Generate memo"}
          </button>
          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
        </form>

        {memo && editableContent ? (
          <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">Memo controls</p>
            <p className="mt-2 text-sm text-neutral-700">Status: {memo.status}</p>
            {memo.source_run_id ? (
              <a
                className="mt-1 block text-xs font-semibold text-[var(--accent)]"
                href={`/matters/${matterId}/ai-runs/${memo.source_run_id}`}
              >
                AI run: {memo.source_run_id}
              </a>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                disabled={isSaving}
                type="button"
                onClick={saveMemo}
              >
                {isSaving ? "Saving..." : "Save edits"}
              </button>
              <a
                className="rounded-full border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--accent)]"
                href={`/api/memos/${memo.id}/export.md`}
              >
                Export Markdown
              </a>
              <a
                className="rounded-full border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--accent)]"
                href={`/api/memos/${memo.id}/export.docx`}
              >
                Export DOCX
              </a>
            </div>
          </article>
        ) : null}
      </section>

      <section className="rounded-3xl border border-[var(--border)] bg-white p-5">
        {editableContent ? (
          <MemoEditor content={editableContent} onChange={setEditableContent} />
        ) : (
          <div className="text-sm leading-7 text-neutral-600">
            Generate a memo to review the required sections, inspect citations, edit the draft,
            and export a working artifact.
          </div>
        )}
      </section>
    </div>
  );
}

function MemoEditor({
  content,
  onChange,
}: {
  content: MemoContent;
  onChange: (content: MemoContent) => void;
}) {
  return (
    <div className="space-y-6">
      <label className="block text-sm font-semibold">
        Issue
        <textarea
          className="mt-2 min-h-20 w-full rounded-2xl border border-[var(--border)] px-4 py-3 text-sm leading-6"
          value={content.issue}
          onChange={(event) => onChange({ ...content, issue: event.target.value })}
        />
      </label>
      <label className="block text-sm font-semibold">
        Answer in Brief
        <textarea
          className="mt-2 min-h-28 w-full rounded-2xl border border-[var(--border)] px-4 py-3 text-sm leading-6"
          value={content.answer_in_brief}
          onChange={(event) => onChange({ ...content, answer_in_brief: event.target.value })}
        />
      </label>
      <FactSection title="Supporting Facts" facts={content.supporting_facts} />
      <FactSection title="Contrary Facts" facts={content.contrary_facts} />
      <ListSection title="Gaps" items={content.gaps} />
      <ListSection title="Next Documents to Review" items={content.next_documents_to_review} />
    </div>
  );
}

function FactSection({ title, facts }: { title: string; facts: MemoFact[] }) {
  return (
    <section>
      <h3 className="text-lg font-semibold">{title}</h3>
      <div className="mt-3 space-y-3">
        {facts.map((fact, index) => (
          <article key={`${fact.statement}-${index}`} className="rounded-2xl bg-[var(--muted)] p-4">
            <p className="text-sm leading-6 text-neutral-800">{fact.statement}</p>
            <div className="mt-3 space-y-2">
              {fact.citations.map((citation) => (
                <div key={citation.id ?? citation.quote} className="rounded-2xl bg-white p-3">
                  <p className="text-sm font-semibold">{citation.document_name}</p>
                  <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                    Page {citation.page ?? "n/a"} · {citation.validation_status ?? "validated"}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-neutral-700">{citation.quote}</p>
                  {citation.viewer_url ? (
                    <a
                      className="mt-3 inline-flex rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                      href={citation.viewer_url}
                    >
                      Open citation
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h3 className="text-lg font-semibold">{title}</h3>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-neutral-700">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

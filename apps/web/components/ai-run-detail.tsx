"use client";

import { useEffect, useState } from "react";

type AIRun = {
  id: string;
  matter_id: string;
  run_type: string;
  model_name: string;
  prompt_template_version: string;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  token_usage_json: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
};

export function AIRunDetail({ runId }: { runId: string }) {
  const [run, setRun] = useState<AIRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadRun() {
      const response = await fetch(`/api/ai-runs/${runId}`, { cache: "no-store" });
      if (!isMounted) {
        return;
      }
      setIsLoading(false);
      if (response.status === 401) {
        window.location.assign("/sign-in");
        return;
      }
      if (!response.ok) {
        setError("Trace could not load this AI run.");
        return;
      }
      setRun(await response.json());
    }

    loadRun().catch(() => {
      if (isMounted) {
        setIsLoading(false);
        setError("Trace could not load this AI run.");
      }
    });

    return () => {
      isMounted = false;
    };
  }, [runId]);

  if (isLoading) {
    return <p className="text-sm text-neutral-600">Loading AI run...</p>;
  }

  if (error) {
    return <p className="rounded-2xl bg-red-50 p-4 text-sm text-red-700">{error}</p>;
  }

  if (!run) {
    return <p className="text-sm text-neutral-600">AI run not found.</p>;
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-3 rounded-3xl border border-[var(--border)] bg-white p-5 md:grid-cols-2">
        <RunField label="Status" value={run.status} />
        <RunField label="Workflow" value={run.run_type} />
        <RunField label="Prompt" value={run.prompt_template_version} />
        <RunField label="Model" value={run.model_name} />
        <RunField label="Created" value={new Date(run.created_at).toLocaleString()} />
        <RunField label="Error" value={run.error_message ?? "none"} />
      </section>
      <JsonPanel title="Input" value={run.input_json} />
      <JsonPanel title="Output" value={run.output_json} />
      <JsonPanel title="Token Usage" value={run.token_usage_json} />
    </div>
  );
}

function RunField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-neutral-800">{value}</p>
    </div>
  );
}

function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <section className="rounded-3xl border border-[var(--border)] bg-white p-5">
      <h3 className="text-lg font-semibold">{title}</h3>
      <pre className="mt-4 max-h-[32rem] overflow-auto rounded-2xl bg-[var(--muted)] p-4 text-xs leading-6 text-neutral-700">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

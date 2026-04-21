"use client";

import { useEffect, useState } from "react";

type AuditLog = {
  id: string;
  user_id: string | null;
  matter_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export function AuditTrail({ matterId }: { matterId: string }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadAudit() {
      const response = await fetch(`/api/audit?matter_id=${matterId}&limit=100`, { cache: "no-store" });
      if (!isMounted) {
        return;
      }
      setIsLoading(false);
      if (response.status === 401) {
        window.location.assign("/sign-in");
        return;
      }
      if (!response.ok) {
        setError("Trace could not load the audit trail.");
        return;
      }
      setLogs(await response.json());
    }

    loadAudit().catch(() => {
      if (isMounted) {
        setIsLoading(false);
        setError("Trace could not load the audit trail.");
      }
    });

    return () => {
      isMounted = false;
    };
  }, [matterId]);

  if (isLoading) {
    return <p className="text-sm text-neutral-600">Loading audit trail...</p>;
  }

  if (error) {
    return <p className="rounded-2xl bg-red-50 p-4 text-sm text-red-700">{error}</p>;
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-neutral-700">{logs.length} recent matter audit events</p>
        <a
          className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
          href={`/api/audit/export.csv?matter_id=${matterId}`}
        >
          Export Audit CSV
        </a>
      </div>
      <div className="overflow-hidden rounded-3xl border border-[var(--border)] bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-[var(--muted)]">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Target</th>
              <th className="px-4 py-3">Metadata</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-t border-[var(--border)]">
                <td className="px-4 py-3 align-top text-neutral-600">
                  {new Date(log.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3 align-top font-semibold">{log.action}</td>
                <td className="px-4 py-3 align-top text-neutral-700">
                  {log.target_type ?? "n/a"}
                  {log.target_id ? <span className="block text-xs text-neutral-500">{log.target_id}</span> : null}
                </td>
                <td className="max-w-sm px-4 py-3 align-top text-xs text-neutral-600">
                  <code className="break-words">{JSON.stringify(log.metadata_json)}</code>
                </td>
              </tr>
            ))}
            {logs.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-neutral-600" colSpan={4}>
                  No audit events are recorded for this matter yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

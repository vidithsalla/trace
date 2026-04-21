"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Matter = {
  id: string;
  name: string;
  description?: string | null;
  matter_code?: string | null;
  status: string;
  role?: string | null;
  created_at: string;
};

export function MatterList() {
  const [matters, setMatters] = useState<Matter[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadMatters() {
      const response = await fetch("/api/matters", { cache: "no-store" });
      if (!isMounted) {
        return;
      }
      setIsLoading(false);
      if (response.status === 401) {
        window.location.assign("/sign-in");
        return;
      }
      if (!response.ok) {
        setError("Unable to load matters.");
        return;
      }
      setMatters(await response.json());
    }

    loadMatters().catch(() => {
      if (isMounted) {
        setIsLoading(false);
        setError("Unable to load matters.");
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return <MatterSkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (matters.length === 0) {
    return (
      <div className="rounded-3xl border border-[var(--border)] bg-[var(--panel)] p-6">
        <p className="text-sm text-neutral-700">
          No matters yet. Create one to start a private Trace workspace.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      {matters.map((matter) => (
        <Link
          className="rounded-3xl border border-[var(--border)] bg-[var(--panel)] p-6 shadow-[0_10px_30px_rgba(29,29,26,0.06)] transition hover:-translate-y-0.5"
          href={`/matters/${matter.id}/documents`}
          key={matter.id}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--warm)]">
                {matter.matter_code ?? "Matter"}
              </p>
              <h3 className="mt-2 text-2xl font-semibold">{matter.name}</h3>
              {matter.description ? (
                <p className="mt-3 max-w-3xl text-sm leading-6 text-neutral-700">
                  {matter.description}
                </p>
              ) : null}
            </div>
            <div className="flex gap-2 text-xs uppercase tracking-[0.18em]">
              <span className="rounded-full border border-[var(--border)] px-3 py-2">
                {matter.status}
              </span>
              <span className="rounded-full bg-[var(--muted)] px-3 py-2">
                {matter.role ?? "member"}
              </span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

function MatterSkeleton() {
  return (
    <div className="grid gap-5">
      {[0, 1].map((item) => (
        <div
          className="h-36 animate-pulse rounded-3xl border border-[var(--border)] bg-[var(--panel)]"
          key={item}
        />
      ))}
    </div>
  );
}

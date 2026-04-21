"use client";

import { FormEvent, useState } from "react";

export function MatterCreateForm() {
  const [name, setName] = useState("");
  const [matterCode, setMatterCode] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const response = await fetch("/api/matters", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name,
        matter_code: matterCode || null,
        description: description || null,
      }),
    });

    setIsSubmitting(false);

    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Unable to create matter.");
      return;
    }

    const matter = await response.json();
    window.location.assign(`/matters/${matter.id}/documents`);
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <label className="block">
        <span className="text-sm font-medium text-neutral-800">Matter name</span>
        <input
          className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)]"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Industrial v. Northshore Supply"
          required
        />
      </label>
      <label className="block">
        <span className="text-sm font-medium text-neutral-800">Matter code</span>
        <input
          className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)]"
          value={matterCode}
          onChange={(event) => setMatterCode(event.target.value)}
          placeholder="TRACE-001"
        />
      </label>
      <label className="block">
        <span className="text-sm font-medium text-neutral-800">Description</span>
        <textarea
          className="mt-2 min-h-32 w-full rounded-2xl border border-[var(--border)] bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--accent)]"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Briefly describe the dispute, investigation, or review workspace."
        />
      </label>
      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      <button
        className="rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isSubmitting}
        type="submit"
      >
        {isSubmitting ? "Creating..." : "Create matter"}
      </button>
    </form>
  );
}

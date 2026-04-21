import Link from "next/link";

import { MatterList } from "@/components/matter-list";
import { AppShell } from "@/components/shell";

export default function MattersPage() {
  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--warm)]">Matters</p>
          <h2 className="text-3xl font-semibold">Matter Workspaces</h2>
        </div>
        <Link className="rounded-full bg-[var(--accent)] px-5 py-3 text-sm text-white" href="/matters/new">
          Create Matter
        </Link>
      </div>
      <MatterList />
    </AppShell>
  );
}

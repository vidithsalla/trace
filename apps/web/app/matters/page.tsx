import Link from "next/link";

import { MatterList } from "@/components/matter-list";
import { AppShell } from "@/components/shell";
import { PageHeader } from "@/components/v3/ui";

export default function MattersPage() {
  return (
    <AppShell>
      <PageHeader
        title="Matters"
        description="Each matter has its own documents, members and review history. Nothing is shared across matters."
        actions={
          <Link
            className="inline-flex h-8 items-center rounded-md bg-[var(--primary)] px-3 text-sm font-medium text-white hover:bg-[var(--primary-hover)]"
            href="/matters/new"
          >
            New matter
          </Link>
        }
      />
      <MatterList />
    </AppShell>
  );
}

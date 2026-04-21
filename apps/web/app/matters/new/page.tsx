import { MatterCreateForm } from "@/components/matter-create-form";
import { AppShell, PageCard } from "@/components/shell";

export default function NewMatterPage() {
  return (
    <AppShell>
      <PageCard eyebrow="Matter Creation" title="Create a new matter">
        <p className="mb-6 text-sm leading-7 text-neutral-700">
          Create a private matter workspace. Trace will automatically add you as the matter admin for
          the new workspace.
        </p>
        <MatterCreateForm />
      </PageCard>
    </AppShell>
  );
}

import { SignInForm } from "@/components/sign-in-form";
import { Logo } from "@/components/v3/matter-shell";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2 text-sm font-semibold">
          <Logo /> Trace
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6">
          <h1 className="text-lg font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">Use a seeded demo account. Everything runs on this machine.</p>
          <SignInForm />
        </div>
        <p className="mt-4 text-xs leading-5 text-[var(--muted-foreground)]">
          Demo accounts: attorney@trace.local, reviewer@trace.local, admin@trace.local · password trace-demo-password
        </p>
      </div>
    </div>
  );
}

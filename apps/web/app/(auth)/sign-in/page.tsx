import { SignInForm } from "@/components/sign-in-form";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="w-full max-w-lg rounded-[2rem] border border-[var(--border)] bg-[rgba(255,253,248,0.95)] p-8 shadow-[0_18px_40px_rgba(29,29,26,0.08)]">
        <p className="text-xs uppercase tracking-[0.28em] text-[var(--warm)]">Trace</p>
        <h1 className="mt-2 text-3xl font-semibold">Trace - Sovereign Discovery Copilot</h1>
        <p className="mt-4 text-sm leading-6 text-neutral-700">
          Sign in with a seeded demo account to open matter workspaces. The default local attorney is
          prefilled for Phase 1 validation.
        </p>
        <SignInForm />
        <p className="mt-6 text-xs leading-5 text-neutral-500">
          Other seeded accounts: admin@trace.local and reviewer@trace.local. Password:
          trace-demo-password.
        </p>
      </div>
    </div>
  );
}

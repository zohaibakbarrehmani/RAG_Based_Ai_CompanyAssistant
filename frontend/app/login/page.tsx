"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@company.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"admin" | "employee">("admin");

  function handleTabSelect(role: "admin" | "employee") {
    setActiveTab(role);
    if (role === "admin") {
      setEmail("admin@company.com");
      setPassword("admin123");
    } else {
      setEmail("employee@company.com");
      setPassword("employee123");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        throw new Error(data.detail ?? "Authentication failed");
      }

      const data = (await response.json()) as {
        access_token: string;
        user: { role: string; email: string };
      };

      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user_role", data.user.role);
      localStorage.setItem("user_email", data.user.email);

      if (data.user.role === "admin") {
        router.push("/admin");
        return;
      }

      router.push("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen flex items-center justify-center overflow-hidden bg-[#0a0e17] px-4 py-12 text-slate-100 selection:bg-indigo-500">
      {/* Background Ambient Glows */}
      <div className="pointer-events-none absolute -top-40 -left-40 size-96 rounded-full bg-indigo-600/20 blur-[128px]" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 size-96 rounded-full bg-violet-600/20 blur-[128px]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px] opacity-25" />

      <div className="relative w-full max-w-md">
        {/* Logo & Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-xl shadow-indigo-500/25 ring-1 ring-white/20">
            <svg viewBox="0 0 24 24" fill="none" className="size-7" aria-hidden="true">
              <path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42m0-12.72-1.42 1.42m-9.88 9.88-1.42 1.42" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-indigo-300">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Enterprise Knowledge RAG
          </span>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-3xl">Company Policy AI</h1>
          <p className="mt-1.5 text-xs text-slate-400">
            Instant, verifiable answers grounded in verified company documents
          </p>
        </div>

        {/* Card */}
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-7 shadow-2xl backdrop-blur-xl sm:p-8">
          {/* Preset Selector */}
          <div className="mb-6 grid grid-cols-2 gap-2 rounded-xl bg-slate-950/60 p-1 ring-1 ring-white/5">
            <button
              type="button"
              onClick={() => handleTabSelect("admin")}
              className={`flex items-center justify-center gap-2 rounded-lg py-2.5 text-xs font-semibold transition ${
                activeTab === "admin"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" stroke="currentColor" strokeWidth="1.8" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              Admin Role
            </button>
            <button
              type="button"
              onClick={() => handleTabSelect("employee")}
              className={`flex items-center justify-center gap-2 rounded-lg py-2.5 text-xs font-semibold transition ${
                activeTab === "employee"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" stroke="currentColor" strokeWidth="1.8" />
                <circle cx="9" cy="7" r="4" stroke="currentColor" strokeWidth="1.8" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              Employee Role
            </button>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Email Address
              </label>
              <div className="relative mt-1.5">
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  placeholder="name@company.com"
                  className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Password
              </label>
              <div className="relative mt-1.5">
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>
            </div>

            {error ? (
              <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-300">
                <svg viewBox="0 0 24 24" fill="none" className="size-4 shrink-0 text-red-400 mt-0.5" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M12 8v4m0 4h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <span>{error}</span>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 py-3.5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 transition hover:from-indigo-500 hover:to-violet-500 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <>
                  <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign In as {activeTab === "admin" ? "Admin" : "Employee"}</span>
                  <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                    <path d="M5 12h14m-7-7 7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </>
              )}
            </button>
          </form>

          {/* Seed credentials hint */}
          <div className="mt-6 rounded-xl border border-white/5 bg-slate-950/40 p-3 text-center">
            <p className="text-[11px] text-slate-400">
              Testing demo? Switch tabs above to auto-fill <span className="font-mono text-indigo-300">admin@company.com</span> or <span className="font-mono text-indigo-300">employee@company.com</span>.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

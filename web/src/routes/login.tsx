import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/overheard/Logo";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [
    { title: "Sign in | ReplyInPublic" },
    { name: "robots", content: "noindex, follow" },
    { name: "description", content: "Sign in to ReplyInPublic to read public customer comments." },
  ] }),
  component: Login,
});

function Login() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/desk/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!r.ok) {
        setError(r.status === 401 ? "That username and password don't match." : "Could not sign in. Try again.");
        return;
      }
      qc.clear();
      await navigate({ to: "/inbox" });
    } catch {
      setError("Could not sign in. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "block w-full rounded-sm border bg-card px-3 py-2 text-sm outline-none focus:border-stamp";
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <Link to="/" aria-label="ReplyInPublic home" className="mb-8 block">
          <Logo className="mx-auto" />
        </Link>
        <form onSubmit={submit} className="space-y-4 rounded-sm border bg-card p-6">
          <h1 className="font-serif text-2xl">Sign in</h1>
          <label className="block space-y-1 text-sm">
            Username
            <input className={field} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" autoFocus required />
          </label>
          <label className="block space-y-1 text-sm">
            Password
            <input className={field} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p role="alert" className="text-sm text-stamp">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Brand teams see their own brand. The ReplyInPublic team sees every brand it works on.
        </p>
      </div>
    </main>
  );
}

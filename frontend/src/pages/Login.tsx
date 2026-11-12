import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useAction } from "../hooks/useLoad";

export function Login() {
  const { needsSetup, signIn, setup } = useAuth();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void action.run(() => (needsSetup ? setup(email, name, password) : signIn(email, password)));
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Creator Finder</h1>
          <p className="mt-1 text-sm text-slate-500">
            {needsSetup ? "First run: create the administrator account." : "Sign in to continue."}
          </p>
        </div>
        {needsSetup && (
          <Field label="Your name"><Input value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" /></Field>
        )}
        <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></Field>
        <Field label="Password" hint={needsSetup ? "At least 8 characters." : undefined}>
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={needsSetup ? 8 : 1}
            autoComplete={needsSetup ? "new-password" : "current-password"} />
        </Field>
        <ErrorNote error={action.error} />
        <Button type="submit" className="w-full" disabled={action.busy}>
          {action.busy ? "Please wait…" : needsSetup ? "Create account" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}

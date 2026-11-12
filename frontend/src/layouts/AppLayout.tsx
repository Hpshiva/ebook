import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const TEAM_NAV = [
  ["/", "Overview"],
  ["/discover", "Discover Creators"],
  ["/creators", "Creator Database"],
  ["/review", "Needs Review"],
  ["/campaigns", "Campaigns"],
  ["/clients", "Clients"],
  ["/outreach", "Outreach"],
  ["/partnerships", "Partnerships"],
  ["/reports", "Reports"],
  ["/costs", "Cost & Usage"],
  ["/settings", "Settings"],
] as const;

const CLIENT_NAV = [["/", "My Campaigns"]] as const;

export function AppLayout() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const nav = user?.role === "client" ? CLIENT_NAV : TEAM_NAV;

  return (
    <div className="min-h-screen bg-slate-50 lg:flex">
      <header className="flex items-center justify-between bg-slate-900 px-4 py-3 text-white lg:hidden">
        <span className="font-semibold">Creator Finder</span>
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Toggle navigation"
          className="rounded-md px-2 py-1 text-sm ring-1 ring-slate-600">Menu</button>
      </header>

      <aside className={`${open ? "block" : "hidden"} w-full shrink-0 bg-slate-900 text-slate-300 lg:sticky lg:top-0 lg:block lg:h-screen lg:w-60`}>
        <div className="hidden px-5 py-5 lg:block">
          <p className="text-base font-semibold text-white">Creator Finder</p>
          <p className="text-xs text-slate-400">Creator discovery & CRM</p>
        </div>
        <nav aria-label="Main" className="space-y-0.5 px-3 pb-3">
          {nav.map(([to, text]) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-800 font-medium text-white" : "hover:bg-slate-800/60 hover:text-white"}`}>
              {text}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 px-5 py-4 text-xs lg:absolute lg:bottom-0 lg:w-60">
          <p className="truncate font-medium text-slate-200">{user?.name || user?.email}</p>
          <p className="capitalize text-slate-400">{user?.role}</p>
          <button type="button" onClick={signOut} className="mt-2 text-slate-300 underline hover:text-white">Sign out</button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

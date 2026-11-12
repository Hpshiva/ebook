import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { CreatorCard } from "../components/CreatorCard";
import { ExportButtons } from "../components/shared";
import { AuthProvider } from "../hooks/useAuth";
import type { Creator, Settings } from "../types";

// ---- A tiny fake backend: every test declares the routes it needs. -------------
type Handler = (body?: unknown, params?: Record<string, unknown>) => unknown;
const routes = new Map<string, Handler>();
const calls: { method: string; url: string; body?: unknown; params?: Record<string, unknown> }[] = [];
const downloadExport = vi.fn(async (_params: Record<string, unknown>) => {});

function dispatch(method: string, url: string, body?: unknown, params?: Record<string, unknown>) {
  calls.push({ method, url, body, params });
  const handler = routes.get(`${method} ${url}`);
  if (!handler) return Promise.reject(new Error(`No fake route for ${method} ${url}`));
  try {
    return Promise.resolve(handler(body, params));
  } catch (e) {
    return Promise.reject(e);
  }
}

vi.mock("../services/api", () => ({
  api: {
    get: (url: string, params?: Record<string, unknown>) => dispatch("GET", url, undefined, params),
    post: (url: string, body?: unknown) => dispatch("POST", url, body),
    put: (url: string, body?: unknown) => dispatch("PUT", url, body),
    patch: (url: string, body?: unknown) => dispatch("PATCH", url, body),
    del: (url: string) => dispatch("DELETE", url),
  },
  downloadExport: (params: Record<string, unknown>) => downloadExport(params),
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : "Something went wrong"),
  setUnauthorizedHandler: () => {},
  tokenStore: { get: () => "token", set: () => {}, clear: () => {} },
}));

const creator = (over: Partial<Creator> = {}): Creator => ({
  id: 1, username: "demo_fitness_aarav", full_name: "Aarav Mehta (Demo)", profile_url: "https://www.instagram.com/demo_fitness_aarav/",
  profile_pic_url: "", followers: 42000, median_reel_views: 91000, reels_analyzed: 5, engagement_rate: 4.2, niche: "fitness",
  country: "India", language: "Hindi", business_category: "Fitness Trainer", selling_status: "NOT_SELLING", selling_overridden: false,
  has_email: true, email: "hello@demo.example", lead_score: 92, confidence: "High", verdict: "qualified",
  verdict_reasons: ["Meets all active filters."], crm_status: "Qualified", tags: [], owner_id: null, follow_up_date: null,
  is_demo: true, source: "demo", collected: true, last_collected_at: "2026-11-12T08:00:00", created_at: "2026-11-12T08:00:00", ...over,
});

const settings: Settings = {
  filters: { min_followers: 10000, max_followers: 100000, min_views: 50000, max_views: 200000, min_reels: 2, require_email: true, no_email_to_review: true, require_public: true, exclude_selling: true },
  scoring_weights: { follower_fit: 10, reel_views: 25, engagement: 20, niche_relevance: 20, selling_status: 15, contact: 10 },
  cache_days: 14, max_profiles_per_search: 50, collect_phone: false, provider_mode: "mock", monthly_budget_inr: 0, budget_warn_pct: 80,
  fx: { usd_inr: 90, updated_at: null, source: "manual default" }, apify_pricing: { usd_per_profile: null, source: null, updated_at: null },
  sender_name: "", apify_token_configured: false, reels_per_creator: 5,
};

const meta = {
  crm_statuses: ["New", "Needs Review", "Qualified", "Not Qualified", "Contacted", "Rejected"],
  selling_statuses: ["SELLING", "CHECK", "NOT_SELLING", "UNKNOWN"], niches: ["fitness", "food"], demo_niches: ["fitness"],
  countries: ["India"], languages: ["Hindi"], owners: [{ id: 1, name: "Admin" }],
};

const dashboard = {
  creators_total: 6, demo_creators: 6, qualified: 2, needs_review: 2, rejected: 2, with_email: 5, searches: 1, active_campaigns: 1, clients: 1,
  crm_statuses: { Qualified: 2, "Needs Review": 2 }, outreach: { draft: 0, contacted: 0, replied: 0, no_reply: 0 }, follow_ups_due: 0,
  cost: { best_known_usd: 0, best_known_inr: 0, has_actuals: false, live_searches: 0 }, provider_mode: "mock",
};

const run = (results: Creator[]) => ({
  id: 7, created_at: "2026-11-12T08:00:00", campaign_id: null, params: { niche: "fitness" }, discovery_source: "demo", profile_provider: "demo",
  is_demo: true, discovered: results.length, requested: results.length, collected: results.length, cached: 0, failed: 0,
  qualified: results.filter((r) => r.verdict === "qualified").length, needs_review: results.filter((r) => r.verdict === "needs_review").length,
  rejected: results.filter((r) => r.verdict === "rejected").length, actor_runs: 0, est_cost_usd: null, actual_cost_usd: null,
  messages: ["DEMO DATA: these are fictional sample creators, not real Instagram accounts."], results,
});

function signedIn(role: "admin" | "client" = "admin") {
  routes.set("GET /api/auth/status", () => ({ needs_setup: false }));
  routes.set("GET /api/auth/me", () => ({ id: 1, email: "a@test.local", name: "Admin", role, client_id: role === "client" ? 3 : null, is_active: true }));
  routes.set("GET /api/settings", () => settings);
  routes.set("GET /api/meta", () => meta);
  routes.set("GET /api/campaigns", () => [{ id: 4, name: "Acme launch", niche: "fitness", product_name: "", status: "Active", client_id: 3,
    client_name: "Acme", type: "client", target_leads: 100, creators: 0, shortlisted: 0, approved: 0, rejected: 0, created_at: "2026-11-12T08:00:00" }]);
  routes.set("GET /api/clients", () => [{ id: 3, name: "Acme", contact_name: "", email: "", notes: "", status: "Active", campaigns: 1 }]);
  routes.set("GET /api/dashboard", () => dashboard);
}

const renderApp = (path = "/") =>
  render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);

beforeEach(() => {
  routes.clear();
  calls.length = 0;
  downloadExport.mockClear();
});

describe("creator card", () => {
  it("shows the key facts, the DEMO DATA label and working action buttons", async () => {
    const onAdd = vi.fn(), onApprove = vi.fn(), onReject = vi.fn();
    render(<MemoryRouter><CreatorCard creator={creator()} onAddToCampaign={onAdd} onApprove={onApprove} onReject={onReject} /></MemoryRouter>);
    expect(screen.getByText("@demo_fitness_aarav")).toBeInTheDocument();
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
    expect(screen.getByText("42K")).toBeInTheDocument();
    expect(screen.getByText("91K")).toBeInTheDocument();
    expect(screen.getByText("Not selling")).toBeInTheDocument();
    expect(screen.getByText("Public email")).toBeInTheDocument();
    expect(screen.getByText("92")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View profile" })).toHaveAttribute("href", "/creators/1");
    await userEvent.click(screen.getByRole("button", { name: "Add to campaign" }));
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onAdd).toHaveBeenCalledOnce();
    expect(onApprove).toHaveBeenCalledOnce();
    expect(onReject).toHaveBeenCalledOnce();
  });

  it("never shows missing data as zero", () => {
    render(<MemoryRouter><CreatorCard creator={creator({ is_demo: false, collected: false, followers: null, median_reel_views: null,
      lead_score: null, has_email: false, verdict: "needs_review", selling_status: "UNKNOWN", last_collected_at: null })} /></MemoryRouter>);
    expect(screen.queryByText("DEMO DATA")).not.toBeInTheDocument();
    expect(screen.getByText("No score")).toBeInTheDocument();
    expect(screen.getByText("Profile data not collected")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(3);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});

describe("sign in", () => {
  it("offers first-run setup and signs the admin in", async () => {
    routes.set("GET /api/auth/status", () => ({ needs_setup: true }));
    routes.set("GET /api/auth/me", () => { throw new Error("401"); });
    routes.set("POST /api/auth/setup", () => ({ token: "t", user: { id: 1, email: "a@test.local", name: "Amit", role: "admin", client_id: null, is_active: true } }));
    signedInAfterSetup();
    renderApp();
    expect(await screen.findByText(/create the administrator account/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your name"), "Amit");
    await userEvent.type(screen.getByLabelText("Email"), "a@test.local");
    await userEvent.type(screen.getByLabelText(/^Password/), "long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/auth/setup")?.body).toEqual({ email: "a@test.local", name: "Amit", password: "long-enough-password" });
  });

  it("shows the server's error when the password is wrong", async () => {
    routes.set("GET /api/auth/status", () => ({ needs_setup: false }));
    routes.set("GET /api/auth/me", () => { throw new Error("401"); });
    routes.set("POST /api/auth/login", () => { throw new Error("Incorrect email or password"); });
    renderApp();
    await userEvent.type(await screen.findByLabelText("Email"), "a@test.local");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });
});

function signedInAfterSetup() {
  routes.set("GET /api/dashboard", () => dashboard);
  routes.set("GET /api/campaigns", () => []);
}

describe("navigation", () => {
  it("has every section in the sidebar and moves between pages", async () => {
    signedIn();
    routes.set("GET /api/creators", () => ({ total: 1, page: 1, page_size: 25, items: [creator()] }));
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of ["Overview", "Discover Creators", "Creator Database", "Needs Review", "Campaigns", "Clients", "Outreach",
      "Partnerships", "Reports", "Cost & Usage", "Settings"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(await screen.findByText("Creators discovered")).toBeInTheDocument();
    expect(screen.getByText("6 are demo data")).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: "Creator Database" }));
    expect(await screen.findByRole("heading", { name: "Creator Database" })).toBeInTheDocument();
    expect(await screen.findByText("@demo_fitness_aarav")).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: "Clients" }));
    expect(await screen.findByRole("heading", { name: "Clients" })).toBeInTheDocument();
    expect(await screen.findByText("Acme")).toBeInTheDocument();
  });

  it("gives a client user only their campaigns", async () => {
    signedIn("client");
    renderApp("/settings");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link")).toHaveLength(1);
    expect(await screen.findByRole("heading", { name: "My Campaigns" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New campaign" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.url === "/api/settings" || c.url === "/api/clients")).toBe(false);
  });
});

describe("discover", () => {
  it("sends the edited filters, shows results and lets a lead be approved", async () => {
    signedIn();
    const results = [creator(), creator({ id: 2, username: "demo_fitness_priya", verdict: "needs_review", selling_status: "CHECK", crm_status: "Needs Review" }),
      creator({ id: 3, username: "demo_fitness_oliver", verdict: "rejected", selling_status: "SELLING" })];
    routes.set("POST /api/discovery/run", () => ({ needs_confirmation: false, run: run(results) }));
    routes.set("PATCH /api/creators/2", (body) => ({ ...results[1], ...(body as object) }));
    renderApp("/discover");

    const min = await screen.findByLabelText("Min followers");
    await userEvent.clear(min);
    await userEvent.type(min, "20000");
    await userEvent.click(screen.getByLabelText("Require a public email"));
    await userEvent.click(screen.getByRole("button", { name: "Run search" }));

    expect(await screen.findAllByTestId("creator-card")).toHaveLength(3);
    const sent = calls.find((c) => c.url === "/api/discovery/run")?.body as { filters: Settings["filters"]; confirmed: boolean; niche: string };
    expect(sent.filters.min_followers).toBe(20000);
    expect(sent.filters.require_email).toBe(false);
    expect(sent.confirmed).toBe(false);
    expect(sent.niche).toBe("fitness");
    expect(screen.getByText(/DEMO DATA: these are fictional/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Needs review (1)" }));
    const cards = screen.getAllByTestId("creator-card");
    expect(cards).toHaveLength(1);
    await userEvent.click(within(cards[0]).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("@demo_fitness_priya marked Qualified.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ crm_status: "Qualified" });

    await userEvent.click(screen.getAllByRole("button", { name: "Export Excel" })[0]);
    expect(downloadExport).toHaveBeenCalledWith({ scope: "search", run_id: 7, fmt: "xlsx" });
  });

  it("asks for confirmation before an external call and shows why it is blocked", async () => {
    signedIn();
    routes.set("POST /api/discovery/run", () => ({ needs_confirmation: true, allowed: false, external_calls: ["Apify profile and reel collection"],
      max_profiles: 12, estimate: { profiles_to_fetch: 12, usd_per_profile: null, pricing_source: null, estimated_usd: null, estimated_inr: null, large_search: false },
      reasons: ["Live providers are switched off (Settings → Provider mode). Demo mode is active."], limits: null }));
    renderApp("/discover");
    await userEvent.selectOptions(await screen.findByLabelText("Discovery source"), "manual");
    await userEvent.type(screen.getByLabelText("Usernames"), "@someone");
    await userEvent.selectOptions(screen.getByLabelText("Profile data provider"), "apify");
    await userEvent.click(screen.getByRole("button", { name: "Run search" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm external calls" });
    expect(within(dialog).getByText("Apify profile and reel collection")).toBeInTheDocument();
    expect(within(dialog).getByText(/Live providers are switched off/)).toBeInTheDocument();
    expect(within(dialog).getByText(/no cost estimate is available/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Run without collection" })).toBeInTheDocument();
    expect(calls.filter((c) => c.url === "/api/discovery/run")).toHaveLength(1);
  });

  it("offers Instagram hashtag search with a hashtags field and Apify as the provider", async () => {
    signedIn();
    routes.set("POST /api/discovery/run", () => ({ needs_confirmation: true, allowed: true, external_calls: ["Apify hashtag search", "Apify profile and reel collection"],
      max_profiles: 50, estimate: { profiles_to_fetch: 50, usd_per_profile: 0.0026, pricing_source: "Apify", estimated_usd: 0.911, estimated_inr: 81.99,
        profiles_usd: 0.13, reels_usd_max: 0.652, discovery_usd: 0.13, large_search: true }, reasons: [], limits: { limit_usd: 5, used_usd: 0.1, remaining_usd: 4.9 } }));
    renderApp("/discover");
    await userEvent.selectOptions(await screen.findByLabelText("Discovery source"), "hashtag");
    expect(screen.getByLabelText("Profile data provider")).toHaveValue("apify");
    await userEvent.type(screen.getByLabelText("Hashtags"), "homeworkout");
    await userEvent.click(screen.getByRole("button", { name: "Run search" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm external calls" });
    expect(within(dialog).getByText(/Hashtag search: \$0.13/)).toBeInTheDocument();
    expect(within(dialog).getByText(/up to \$0.911/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Confirm and run" })).toBeInTheDocument();
    expect((calls.find((c) => c.url === "/api/discovery/run")?.body as { hashtags: string }).hashtags).toBe("homeworkout");
  });

  it("shows a readable error when the search fails", async () => {
    signedIn();
    routes.set("POST /api/discovery/run", () => { throw new Error("Cannot reach the server. Is the backend running?"); });
    renderApp("/discover");
    await userEvent.click(await screen.findByRole("button", { name: "Run search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });
});

describe("review, campaigns and exports", () => {
  it("approves a creator from the Needs Review queue", async () => {
    signedIn();
    const waiting = creator({ id: 2, username: "demo_fitness_priya", verdict: "needs_review", crm_status: "Needs Review" });
    routes.set("GET /api/creators", () => ({ total: 1, page: 1, page_size: 25, items: [waiting] }));
    routes.set("PATCH /api/creators/2", () => ({ ...waiting, crm_status: "Qualified" }));
    renderApp("/review");
    expect(await screen.findByRole("heading", { name: "Needs Review" })).toBeInTheDocument();
    await waitFor(() => expect(calls.find((c) => c.url === "/api/creators")?.params?.verdict).toBe("needs_review"));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("@demo_fitness_priya moved to Qualified.")).toBeInTheDocument();
  });

  it("creates a campaign for a client", async () => {
    signedIn();
    routes.set("POST /api/campaigns", (body) => ({ id: 9, ...(body as object) }));
    renderApp("/campaigns");
    expect(await screen.findByText("Acme launch")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New campaign" }));
    const dialog = screen.getByRole("dialog", { name: "New campaign" });
    await userEvent.type(within(dialog).getByLabelText("Campaign name"), "Diwali fitness push");
    await userEvent.selectOptions(within(dialog).getByLabelText("Client"), "3");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save campaign" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/campaigns")?.body).toMatchObject({ name: "Diwali fitness push", client_id: 3 });
  });

  it("exports in both formats and reports a failed download", async () => {
    render(<ExportButtons params={{ scope: "qualified" }} />);
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(downloadExport).toHaveBeenLastCalledWith({ scope: "qualified", fmt: "csv" });
    downloadExport.mockRejectedValueOnce(new Error("Request failed (500)"));
    await userEvent.click(screen.getByRole("button", { name: "Export Excel" }));
    expect(await screen.findByText("Request failed (500)")).toBeInTheDocument();
  });

  it("shows an empty state when there is nothing to list", async () => {
    signedIn();
    routes.set("GET /api/creators", () => ({ total: 0, page: 1, page_size: 25, items: [] }));
    renderApp("/creators");
    expect(await screen.findByText("No creators match")).toBeInTheDocument();
  });
});

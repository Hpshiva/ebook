export type Role = "admin" | "staff" | "client";
export type Verdict = "qualified" | "needs_review" | "rejected";
export type SellingStatus = "SELLING" | "CHECK" | "NOT_SELLING" | "UNKNOWN";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  client_id: number | null;
  is_active: boolean;
}

export interface Contact {
  id: number;
  type: string;
  value: string;
  source: string;
  source_url: string;
  validation_status: string;
  discovered_at: string | null;
}

export interface ScorePart {
  weight: number;
  points: number | null;
  note: string;
}

export interface Creator {
  id: number;
  username: string;
  full_name: string;
  profile_url: string;
  profile_pic_url: string;
  followers: number | null;
  median_reel_views: number | null;
  reels_analyzed: number;
  engagement_rate: number | null;
  niche: string;
  country: string;
  language: string;
  business_category: string;
  selling_status: SellingStatus;
  selling_overridden: boolean;
  has_email: boolean;
  email: string | null;
  lead_score: number | null;
  confidence: string;
  verdict: Verdict;
  verdict_reasons: string[];
  crm_status: string;
  tags: string[];
  owner_id: number | null;
  follow_up_date: string | null;
  is_demo: boolean;
  source: string;
  collected: boolean;
  last_collected_at: string | null;
  created_at: string | null;
  from_cache?: boolean;
  similarity?: number;
  similar_reasons?: string[];
}

export interface CreatorDetail extends Creator {
  biography: string;
  following: number | null;
  posts_count: number | null;
  external_urls: string[];
  is_verified: boolean | null;
  is_private: boolean | null;
  sub_niche: string;
  reel_views: number[];
  data_provider: string;
  selling_detected: SellingStatus;
  selling_reasons: string[];
  selling_override: { status: SellingStatus; by: string; at: string; note: string } | null;
  score_breakdown: Record<string, ScorePart>;
  contacts: Contact[];
  related_usernames: string[];
  activities: { id: number; action: string; detail: string; user_name: string; created_at: string }[];
  history: { collected_at: string; followers: number | null; median_reel_views: number | null; engagement_rate: number | null }[];
  campaigns: { campaign_id: number; name: string; shortlisted: boolean; approval: string }[];
}

export interface Paged<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface Meta {
  crm_statuses: string[];
  selling_statuses: SellingStatus[];
  niches: string[];
  demo_niches: string[];
  countries: string[];
  languages: string[];
  owners: { id: number; name: string }[];
}

export interface SearchRun {
  id: number;
  created_at: string;
  campaign_id: number | null;
  params: Record<string, unknown>;
  discovery_source: string;
  profile_provider: string;
  is_demo: boolean;
  discovered: number;
  requested: number;
  collected: number;
  cached: number;
  failed: number;
  qualified: number;
  needs_review: number;
  rejected: number;
  actor_runs: number;
  est_cost_usd: number | null;
  actual_cost_usd: number | null;
  messages: string[];
  results?: Creator[];
}

export interface Estimate {
  profiles_to_fetch: number;
  usd_per_profile: number | null;
  usd_per_reel?: number | null;
  reels_per_creator?: number;
  profiles_usd?: number | null;
  reels_usd_max?: number | null;
  discovery_usd?: number | null;
  discovery_results?: number;
  is_upper_bound?: boolean;
  pricing_source: string | null;
  estimated_usd: number | null;
  estimated_inr: number | null;
  large_search: boolean;
}

export interface Confirmation {
  needs_confirmation: true;
  allowed: boolean;
  external_calls: string[];
  max_profiles: number;
  estimate: Estimate | null;
  reasons: string[];
  limits: { limit_usd: number; used_usd: number; remaining_usd: number } | null;
  budget?: Budget;
}

export interface Budget {
  monthly_budget_inr: number;
  provider_cost_usd_this_month: number;
  free_allowance_usd: number | null;
  cash_spend_inr_now: number | null;
  cash_spend_inr_after: number;
  percent_of_budget: number;
  level: "ok" | "warning" | "blocked";
}

export interface Client {
  id: number;
  name: string;
  contact_name: string;
  email: string;
  notes: string;
  status: string;
  campaigns: number;
}

export interface Campaign {
  id: number;
  name: string;
  niche: string;
  product_name: string;
  status: string;
  client_id: number | null;
  client_name: string | null;
  type: "client" | "own";
  target_leads: number;
  creators: number;
  shortlisted: number;
  approved: number;
  rejected: number;
  created_at: string;
}

export interface CampaignLink {
  id: number;
  campaign_id: number;
  shortlisted: boolean;
  approval: "pending" | "approved" | "rejected";
  approval_note: string;
  decided_at: string | null;
  creator: Creator;
}

export interface CampaignDetail extends Campaign {
  links: CampaignLink[];
}

export interface OutreachMessage {
  id: number;
  creator_id: number;
  username: string;
  is_demo: boolean;
  subject: string;
  body: string;
  status: string;
  contacted_at: string | null;
  follow_up_date: string | null;
  notes: string;
  created_at: string;
  email: string | null;
}

export interface Template {
  id: number;
  name: string;
  subject: string;
  body: string;
}

export interface Partnership {
  id: number;
  creator_id: number;
  username: string;
  is_demo: boolean;
  product_id: number;
  product_name: string;
  start_date: string | null;
  commission_pct: number;
  fixed_payment: number;
  tracking_url: string;
  promo_code: string;
  clicks: number | null;
  conversions: number | null;
  revenue: number;
  commission_total: number;
  amount_paid: number;
  commission_owed: number;
  net_revenue: number;
  payment_status: string;
  notes: string;
}

export interface Settings {
  filters: {
    min_followers: number;
    max_followers: number;
    min_views: number;
    max_views: number;
    min_reels: number;
    require_email: boolean;
    no_email_to_review: boolean;
    require_public: boolean;
    exclude_selling: boolean;
  };
  scoring_weights: Record<string, number>;
  cache_days: number;
  max_profiles_per_search: number;
  collect_phone: boolean;
  provider_mode: "mock" | "live";
  monthly_budget_inr: number;
  budget_warn_pct: number;
  fx: { usd_inr: number; updated_at: string | null; source: string };
  apify_pricing: { usd_per_profile: number | null; usd_per_reel?: number | null; usd_per_reel_run?: number | null; source: string | null; updated_at: string | null };
  reels_per_creator: number;
  sender_name: string;
  apify_token_configured: boolean;
  apify_token_source?: string | null;
}

export interface Dashboard {
  creators_total: number;
  demo_creators: number;
  qualified: number;
  needs_review: number;
  rejected: number;
  with_email: number;
  searches: number;
  active_campaigns: number;
  clients: number;
  crm_statuses: Record<string, number>;
  outreach: Record<string, number>;
  follow_ups_due: number;
  cost: { best_known_usd: number; best_known_inr: number | null; has_actuals: boolean; live_searches: number };
  provider_mode: string;
}

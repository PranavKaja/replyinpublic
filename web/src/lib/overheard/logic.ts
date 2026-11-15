export type Status = "inbox" | "parked" | "snoozed" | "handled" | "dismissed" | "feedback";
export type View =
  | "inbox"
  | "parked"
  | "snoozed"
  | "handled"
  | "feedback"
  | "pipeline"
  | "issues"
  | "brands"
  | "metrics"
  | "kit";
export type Where = "all" | "owned" | "earned";
export type Sort = "priority" | "oldest" | "newest" | "liked";

export interface Brand {
  id: string;
  slug: string;
  name: string;
  category: string;
  grace_hours: number;
}
export interface Theme {
  id: string;
  brand_id: string;
  name: string;
  summary: string;
}
export interface Mention {
  id: string;
  brand_id: string;
  platform: string;
  surface: string;
  url: string;
  parent_author: string | null;
  parent_title: string | null;
  author: string;
  text: string;
  posted_at: string;
  like_count: number;
  view_count: number;
  brand_replied: boolean | null;
  is_feedback?: boolean;
  reply_text: string | null;
  proof: string;
  type: string;
  urgency: string;
  needs_response: boolean;
  priority: number;
  theme_id: string | null;
  draft: string | null;
  status: string;
  snoozed_until: string | null;
  status_changed_at: string | null;
}

export interface Filters {
  view: View;
  where: Where;
  brand: string;
  platform: string;
  theme: string;
  type?: string;
  reply?: string;
  urgency?: string;
  q: string;
  sort: Sort;
}

export const hoursSince = (iso: string, now = Date.now()) =>
  Math.max(0, Math.floor((now - new Date(iso).getTime()) / 3_600_000));

/** Snoozed items whose time has passed count as inbox again. */
export function effectiveStatus(m: Mention, now = Date.now()): Status {
  if (m.status === "snoozed" && m.snoozed_until && new Date(m.snoozed_until).getTime() <= now)
    return "inbox";
  return m.status as Status;
}

export const isOverdue = (m: Mention, grace: number, now = Date.now()) =>
  m.brand_replied === false && hoursSince(m.posted_at, now) > grace;

/** A buyer is waiting when a purchase question has no confirmed reply. */
export const isBuyerWaiting = (m: Mention) =>
  m.type === "purchase_intent" && m.brand_replied !== true;

const VIEW_STATUS: Partial<Record<View, Status>> = {
  inbox: "inbox",
  parked: "parked",
  snoozed: "snoozed",
  handled: "handled",
  feedback: "feedback",
};

/** Feedback is a tag: a message can be handled (replied) and also kept as feedback. */
export const isFeedback = (m: Mention) => m.status === "feedback" || m.is_feedback === true;

export type ReplyState = "awaiting" | "overdue" | "unconfirmed" | "replied";
export const REPLY_STATES: ReplyState[] = ["awaiting", "overdue", "unconfirmed", "replied"];
export const REPLY_LABEL: Record<ReplyState, string> = {
  awaiting: "Awaiting",
  overdue: "No reply",
  unconfirmed: "Not confirmed",
  replied: "Replied",
};
/** The reply tag on a row and the reply filter both read this, so they cannot disagree. */
export function replyState(m: Mention, grace: number, now = Date.now()): ReplyState {
  if (m.brand_replied === true) return "replied";
  if (m.brand_replied === null) return "unconfirmed";
  return isOverdue(m, grace, now) ? "overdue" : "awaiting";
}

export type Facet = "where" | "brand" | "platform" | "type" | "reply" | "urgency" | "theme";
export type GraceOf = (brandId: string) => number;
const DEFAULT_GRACE: GraceOf = () => 24;

/** True when a message belongs in the current view and passes every filter except `skip`. */
export function matches(
  m: Mention,
  f: Filters,
  graceOf: GraceOf = DEFAULT_GRACE,
  now = Date.now(),
  skip?: Facet,
): boolean {
  const want = VIEW_STATUS[f.view];
  if (f.view === "feedback") {
    if (!isFeedback(m)) return false;
  } else if (want && effectiveStatus(m, now) !== want) return false;
  if (f.view === "inbox" && !m.needs_response) return false;
  if (skip !== "where" && f.where !== "all" && m.surface !== f.where) return false;
  if (skip !== "brand" && f.brand && m.brand_id !== f.brand) return false;
  if (skip !== "platform" && f.platform && m.platform !== f.platform) return false;
  if (skip !== "theme" && f.theme && m.theme_id !== f.theme) return false;
  if (skip !== "type" && f.type && m.type !== f.type) return false;
  if (skip !== "urgency" && f.urgency && m.urgency !== f.urgency) return false;
  if (skip !== "reply" && f.reply && replyState(m, graceOf(m.brand_id), now) !== f.reply)
    return false;
  const q = f.q.trim().toLowerCase();
  if (q && !m.text.toLowerCase().includes(q) && !m.author.toLowerCase().includes(q)) return false;
  return true;
}

const facetValue = (m: Mention, facet: Facet, graceOf: GraceOf, now: number): string =>
  facet === "where"
    ? m.surface
    : facet === "brand"
      ? m.brand_id
      : facet === "reply"
        ? replyState(m, graceOf(m.brand_id), now)
        : facet === "theme"
          ? (m.theme_id ?? "")
          : m[facet];

/** How many messages each option of one filter would show, with the other filters applied. */
export function facetCounts(
  list: Mention[],
  f: Filters,
  facet: Facet,
  graceOf: GraceOf = DEFAULT_GRACE,
  now = Date.now(),
): Record<string, number> {
  const out: Record<string, number> = {};
  let total = 0;
  for (const m of list) {
    if (!matches(m, f, graceOf, now, facet)) continue;
    const v = facetValue(m, facet, graceOf, now);
    out[v] = (out[v] ?? 0) + 1;
    total += 1;
  }
  out[""] = total;
  out["all"] = total;
  return out;
}

export function filterMentions(
  list: Mention[],
  f: Filters,
  now = Date.now(),
  graceOf: GraceOf = DEFAULT_GRACE,
): Mention[] {
  const out = list.filter((m) => matches(m, f, graceOf, now));
  const t = (m: Mention) => new Date(m.posted_at).getTime();
  const sorters: Record<Sort, (a: Mention, b: Mention) => number> = {
    priority: (a, b) => b.priority - a.priority || t(b) - t(a),
    oldest: (a, b) => t(a) - t(b),
    newest: (a, b) => t(b) - t(a),
    liked: (a, b) => b.like_count - a.like_count,
  };
  return out.sort(sorters[f.sort]);
}

export const inboxCount = (list: Mention[], now = Date.now()) =>
  list.filter((m) => m.needs_response && effectiveStatus(m, now) === "inbox").length;

/** Open = directed at the brand and not yet resolved by the team or the brand. */
const isOpen = (m: Mention, now: number) => {
  const st = effectiveStatus(m, now);
  return m.needs_response && (st === "inbox" || st === "parked" || st === "snoozed");
};

export interface IssueStats {
  unanswered: number;
  total: number;
  reach: number;
  likes: number;
  platforms: string[];
  earnedShare: number;
}
export function issueStats(list: Mention[], themeId: string, now = Date.now()): IssueStats {
  const all = list.filter((m) => m.theme_id === themeId);
  const open = all.filter((m) => isOpen(m, now) && m.brand_replied !== true);
  return {
    total: all.length,
    unanswered: open.length,
    reach: open.reduce((s, m) => s + m.view_count, 0),
    likes: open.reduce((s, m) => s + m.like_count, 0),
    platforms: [...new Set(all.map((m) => m.platform))],
    earnedShare: all.length ? all.filter((m) => m.surface === "earned").length / all.length : 0,
  };
}

export interface TeamMetrics {
  open: number;
  overdue: number;
  buyersWaiting: number;
  unansweredReach: number;
  earnedShare: number;
  medianHoursWaiting: number;
  parked: number;
  handledToday: number;
}
export function teamMetrics(list: Mention[], brands: Brand[], now = Date.now()): TeamMetrics {
  const grace = new Map(brands.map((b) => [b.id, b.grace_hours]));
  const open = list.filter((m) => isOpen(m, now) && m.brand_replied !== true);
  const waits = open.map((m) => hoursSince(m.posted_at, now)).sort((a, b) => a - b);
  const mid = waits.length
    ? waits.length % 2
      ? waits[(waits.length - 1) / 2]!
      : Math.round((waits[waits.length / 2 - 1]! + waits[waits.length / 2]!) / 2)
    : 0;
  const dayAgo = now - 86_400_000;
  return {
    open: open.length,
    overdue: open.filter((m) => isOverdue(m, grace.get(m.brand_id) ?? 24, now)).length,
    buyersWaiting: open.filter(isBuyerWaiting).length,
    unansweredReach: open.reduce((s, m) => s + m.view_count, 0),
    earnedShare: open.length ? open.filter((m) => m.surface === "earned").length / open.length : 0,
    medianHoursWaiting: mid,
    parked: list.filter((m) => effectiveStatus(m, now) === "parked").length,
    handledToday: list.filter(
      (m) =>
        m.status === "handled" &&
        m.status_changed_at &&
        new Date(m.status_changed_at).getTime() > dayAgo,
    ).length,
  };
}

export function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1).replace(/\.0$/, "") + "K";
  return String(n);
}

export const PLACEHOLDER_RE = /(\[[^\]]+\])/g;

export type MetricPeriod = "today" | "7" | "30";
/** Metric cohorts use message creation time and UTC calendar boundaries. */
export function mentionsInPeriod(list: Mention[], period: MetricPeriod, now = Date.now()) {
  const start =
    period === "today" ? new Date(now).setUTCHours(0, 0, 0, 0) : now - Number(period) * 86_400_000;
  return list.filter((m) => {
    const at = Date.parse(m.posted_at);
    return at >= start && at <= now;
  });
}

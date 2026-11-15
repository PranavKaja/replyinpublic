import { useState } from "react";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Download, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  compact,
  effectiveStatus,
  issueStats,
  teamMetrics,
  mentionsInPeriod,
  type MetricPeriod,
  type Brand,
  type Mention,
  type Status,
  type Theme,
} from "@/lib/overheard/logic";
import { PlatformIcon, TypeBadge } from "./bits";

function Shell({
  title,
  controls,
  children,
}: {
  title: string;
  controls?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-3xl">{title}</h1>
        {controls}
      </div>
      <div className="mt-6">{children}</div>
    </div>
  );
}

export function IssuesView({
  themes,
  brands,
  mentions,
  open,
}: {
  themes: Theme[];
  brands: Brand[];
  mentions: Mention[];
  open: (id: string) => void;
}) {
  return (
    <Shell
      title="Issues"
      controls={
        <span className="font-mono text-xs text-muted-foreground">
          {themes.filter((t) => brands.some((b) => b.id === t.brand_id)).length} clusters
        </span>
      }
    >
      <div className="space-y-8">
        {brands.map((b) => {
          const ts = themes.filter((t) => t.brand_id === b.id);
          if (!ts.length) return null;
          return (
            <section key={b.id}>
              <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {b.name}
              </h2>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {ts.map((t) => {
                  const s = issueStats(mentions, t.id);
                  const quotes = mentions.filter((m) => m.theme_id === t.id).slice(0, 2);
                  return (
                    <button
                      key={t.id}
                      onClick={() => open(t.id)}
                      className="space-y-3 rounded-sm border bg-card p-4 text-left transition-colors hover:border-foreground/40"
                    >
                      <div className="font-serif text-xl leading-tight">{t.name}</div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
                        <span className="text-stamp">
                          {s.unanswered} / {s.total} unanswered
                        </span>
                        <span>{compact(s.reach)} reach</span>
                        <span className="text-muted-foreground">
                          {Math.round(s.earnedShare * 100)}% on others' posts
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{t.summary}</p>
                      <div className="flex gap-1">
                        {s.platforms.map((p) => (
                          <span key={p} className="rounded-full border px-1.5 py-0.5">
                            <PlatformIcon p={p} />
                          </span>
                        ))}
                      </div>
                      <div className="space-y-1.5 border-t pt-2">
                        {quotes.map((q) => (
                          <p
                            key={q.id}
                            className="line-clamp-2 font-serif text-sm font-semibold tracking-tight"
                          >
                            "{q.text}"
                          </p>
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </Shell>
  );
}

export function BrandsView({
  brands,
  mentions,
  pick,
}: {
  brands: Brand[];
  mentions: Mention[];
  pick: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const rows = brands
    .filter((b) => b.name.toLowerCase().includes(search.toLowerCase()))
    .map((b) => {
      const ms = mentions.filter((m) => m.brand_id === b.id);
      const tm = teamMetrics(ms, [b]);
      return {
        b,
        total: ms.length,
        directed: ms.filter((m) => m.needs_response).length,
        unanswered: ms.filter((m) => m.brand_replied === false && m.needs_response).length,
        unverified: ms.filter((m) => m.brand_replied === null).length,
        buyers: tm.buyersWaiting,
        reach: tm.unansweredReach,
        platforms: [...new Set(ms.map((m) => m.platform))],
      };
    });
  const sum = (k: "total" | "directed" | "unanswered" | "unverified" | "buyers" | "reach") =>
    rows.reduce((s, r) => s + r[k], 0);
  return (
    <Shell
      title="Clients"
      controls={<SearchField label="Search clients" value={search} set={setSearch} />}
    >
      <TooltipProvider>
        <div className="overflow-x-auto rounded-sm border bg-card">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr className="border-b">
                {[
                  "Brand",
                  "Total",
                  "Directed",
                  "Confirmed unanswered",
                  "Unverified",
                  "Buyers waiting",
                  "Unanswered reach",
                  "Platforms",
                ].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.map((r) => (
                <tr
                  key={r.b.id}
                  className="cursor-pointer border-b hover:bg-accent/50"
                  onClick={() => pick(r.b.id)}
                >
                  <td className="px-3 py-2 font-serif text-base">{r.b.name}</td>
                  <td className="px-3 py-2">{r.total}</td>
                  <td className="px-3 py-2">{r.directed}</td>
                  <td className="px-3 py-2 text-stamp">{r.unanswered}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1">
                      {r.unverified}
                      {r.unverified > 5 && (
                        <Tooltip>
                          <TooltipTrigger>
                            <AlertTriangle className="size-3.5 text-amber" />
                          </TooltipTrigger>
                          <TooltipContent>
                            Reply status not confirmed for {r.unverified} messages.
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-buyer">{r.buyers}</td>
                  <td className="px-3 py-2">{compact(r.reach)}</td>
                  <td className="px-3 py-2">
                    <span className="flex gap-1">
                      {r.platforms.map((p) => (
                        <PlatformIcon key={p} p={p} />
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
              <tr className="bg-muted/50 font-semibold">
                <td className="px-3 py-2 font-sans text-xs uppercase tracking-wider">
                  All clients
                </td>
                <td className="px-3 py-2">{sum("total")}</td>
                <td className="px-3 py-2">{sum("directed")}</td>
                <td className="px-3 py-2 text-stamp">{sum("unanswered")}</td>
                <td className="px-3 py-2">{sum("unverified")}</td>
                <td className="px-3 py-2 text-buyer">{sum("buyers")}</td>
                <td className="px-3 py-2">{compact(sum("reach"))}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </TooltipProvider>
    </Shell>
  );
}

const COLS: { s: Status; label: string; tone: string }[] = [
  { s: "inbox", label: "Inbox", tone: "text-stamp" },
  { s: "parked", label: "Parked for reply", tone: "text-amber" },
  { s: "snoozed", label: "Snoozed", tone: "text-muted-foreground" },
  { s: "handled", label: "Handled", tone: "text-foreground" },
  { s: "feedback", label: "Feedback for brand", tone: "text-replied" },
  { s: "dismissed", label: "Not ours", tone: "text-muted-foreground" },
];

export function PipelineView({
  mentions,
  brands,
  move,
  open,
}: {
  mentions: Mention[];
  brands: Map<string, Brand>;
  move: (id: string, s: Status) => void;
  open: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const directed = mentions.filter(
    (m) =>
      m.needs_response &&
      `${m.text} ${m.author} ${brands.get(m.brand_id)?.name}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <Shell
      title="Pipeline"
      controls={<SearchField label="Search pipeline" value={search} set={setSearch} />}
    >
      <div className="flex gap-3 overflow-x-auto pb-4">
        {COLS.map((c) => {
          const items = directed
            .filter((m) => effectiveStatus(m) === c.s)
            .sort((a, b) => +new Date(b.posted_at) - +new Date(a.posted_at));
          return (
            <div
              key={c.s}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => move(e.dataTransfer.getData("text/plain"), c.s)}
              className="flex w-56 shrink-0 flex-col rounded-sm border bg-muted/40"
            >
              <div className="flex items-baseline justify-between border-b px-3 py-2">
                <span className={cn("font-serif text-base", c.tone)}>{c.label}</span>
                <span className="font-mono text-xs text-muted-foreground">{items.length}</span>
              </div>
              <div className="max-h-[70vh] space-y-2 overflow-y-auto p-2">
                {items.map((m) => (
                  <div
                    key={m.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/plain", m.id)}
                    onClick={() => open(m.id)}
                    className="cursor-grab space-y-1.5 rounded-sm border bg-card p-2 text-xs hover:border-foreground/40"
                  >
                    <div className="flex items-center gap-1.5">
                      <TypeBadge type={m.type} />
                      <span className="ml-auto truncate font-medium">
                        {brands.get(m.brand_id)?.name}
                      </span>
                      <PlatformIcon p={m.platform} />
                    </div>
                    <p className="line-clamp-2 text-[12px] leading-snug">{m.text}</p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Shell>
  );
}

export function MetricsView({ mentions, brands }: { mentions: Mention[]; brands: Brand[] }) {
  const [period, setPeriod] = useState<MetricPeriod>("7");
  const t = teamMetrics(mentionsInPeriod(mentions, period), brands);
  const cards: [string, string, string, string?][] = [
    ["Open and unanswered", String(t.open), "Directed at a client, no reply yet"],
    ["Past grace window", String(t.overdue), "Confirmed no reply after 24h", "text-stamp"],
    ["Buyers waiting", String(t.buyersWaiting), "Purchase questions with no answer", "text-buyer"],
    [
      "Unanswered reach",
      compact(t.unansweredReach),
      "Views on threads where complaints sit unanswered",
    ],
    [
      "Found on others' posts",
      `${Math.round(t.earnedShare * 100)}%`,
      "Of open messages, under creators and communities",
    ],
    ["Median wait", `${t.medianHoursWaiting}h`, "Time open messages have been waiting"],
    ["Parked for reply", String(t.parked), "Queued by the team to answer"],
    ["Handled today", String(t.handledToday), "Closed in the last 24 hours", "text-replied"],
  ];
  return (
    <Shell
      title="Team metrics"
      controls={
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Metrics timeframe"
            value={period}
            onChange={(e) => setPeriod(e.target.value as MetricPeriod)}
            className="h-8 rounded-sm border bg-card px-2 text-sm"
          >
            <option value="today">Today</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </select>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              const csv = [
                ["Metric", "Value", "Timeframe"],
                ...cards.map(([label, value]) => [
                  label,
                  value,
                  period === "today" ? "Today" : `Last ${period} days`,
                ]),
              ]
                .map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(","))
                .join("\r\n");
              const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
              const link = document.createElement("a");
              link.href = url;
              link.download = "replyinpublic-team-metrics.csv";
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download /> Export CSV
          </Button>
        </div>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([l, v, d, tone]) => (
          <div key={l} className="rounded-sm border bg-card p-4">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{l}</div>
            <div className={cn("mt-2 font-mono text-4xl", tone)}>{v}</div>
            <div className="mt-1 text-xs text-muted-foreground">{d}</div>
          </div>
        ))}
      </div>
    </Shell>
  );
}

function SearchField({
  label,
  value,
  set,
}: {
  label: string;
  value: string;
  set: (value: string) => void;
}) {
  return (
    <label className="flex max-w-full items-center gap-2 rounded-sm border bg-card px-2">
      <Search className="size-4 text-muted-foreground" />
      <input
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(e) => set(e.target.value)}
        className="min-w-0 bg-transparent py-1.5 text-sm outline-none"
      />
    </label>
  );
}

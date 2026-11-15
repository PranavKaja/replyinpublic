import {
  Inbox,
  Clock,
  CheckCheck,
  MessageSquareReply,
  Layers,
  Building2,
  Moon,
  Sun,
  Bookmark,
  Columns3,
  Gauge,
  BookOpen,
} from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  type Brand,
  type Filters,
  type Mention,
  type Theme,
  type View,
  type Where,
  type Sort,
  type Facet,
  facetCounts,
  REPLY_STATES,
  REPLY_LABEL,
} from "@/lib/overheard/logic";
import { Button } from "@/components/ui/button";
import { Logo } from "./Logo";

interface Props {
  f: Filters;
  set: (p: Partial<Filters>) => void;
  brands: Brand[];
  themes: Theme[];
  mentions: Mention[];
  counts: Record<string, number>;
}

const VIEWS: { id: View; label: string; icon: typeof Inbox }[] = [
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "parked", label: "Parked for reply", icon: Bookmark },
  { id: "snoozed", label: "Snoozed", icon: Clock },
  { id: "handled", label: "Handled", icon: CheckCheck },
  { id: "feedback", label: "Feedback for brand", icon: MessageSquareReply },
];
const OVERVIEWS: { id: View; label: string; icon: typeof Inbox }[] = [
  { id: "pipeline", label: "Pipeline", icon: Columns3 },
  { id: "issues", label: "Issues", icon: Layers },
  { id: "brands", label: "Clients", icon: Building2 },
  { id: "metrics", label: "Team metrics", icon: Gauge },
  { id: "kit", label: "Brand kit", icon: BookOpen },
];

export function Sidebar({ f, set, brands, themes, mentions, counts }: Props) {
  const [dark, setDark] = useState(false);
  const [name, setName] = useState("Pranav Kaja");
  const [role, setRole] = useState("Founder");
  const [available, setAvailable] = useState(true);
  useEffect(() => {
    setName(localStorage.getItem("overheard:name") ?? "Pranav Kaja");
    setRole(localStorage.getItem("overheard:role") ?? "Founder");
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const listView = VIEWS.some((view) => view.id === f.view) || f.view === "pipeline";
  const graceOf = (id: string) => brands.find((b) => b.id === id)?.grace_hours ?? 24;
  const now = Date.now();
  // Each option shows how many messages it would leave, with the other filters still on.
  const count = (facet: Facet) => (listView ? facetCounts(mentions, f, facet, graceOf, now) : undefined);
  const platforms = PLATFORM_ORDER.filter((p) => mentions.some((m) => m.platform === p));
  const issueOptions: [string, string][] = themes
    .filter((t) => !f.brand || t.brand_id === f.brand)
    .map((t) => [t.id, f.brand ? t.name : `${brands.find((b) => b.id === t.brand_id)?.name ?? ""}: ${t.name}`]);
  const active = [f.where !== "all", f.brand, f.platform, f.theme, f.type, f.reply, f.urgency].filter(Boolean).length;

  const item = (active: boolean) =>
    cn(
      "flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left text-sm transition-colors",
      active
        ? "bg-sidebar-accent font-medium text-foreground"
        : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
    );

  return (
    <nav className="flex h-full flex-col gap-3 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden bg-sidebar px-3 py-3">
      <div className="px-2">
        <Logo />
      </div>

      <div className="space-y-0.5">
        {VIEWS.map(({ id, label, icon: I }) => (
          <button
            key={id}
            className={item(f.view === id)}
            onClick={() => set({ view: id, theme: "" })}
          >
            <I className="size-4" /> <span className="flex-1">{label}</span>
            {counts[id] ? (
              <span
                className={cn(
                  "font-mono text-xs",
                  id === "inbox" && "rounded-sm bg-stamp px-1.5 text-primary-foreground",
                )}
              >
                {counts[id]}
              </span>
            ) : null}
          </button>
        ))}
        <div className="my-2 border-t" />
        {OVERVIEWS.map(({ id, label, icon: I }) => (
          <button key={id} className={item(f.view === id)} onClick={() => set({ view: id })}>
            <I className="size-4" /> <span className="flex-1">{label}</span>
          </button>
        ))}
      </div>

      <div className="space-y-2.5 px-2">
        <div className="flex items-center justify-between">
          <Label>Filters</Label>
          {active > 0 && (
            <button
              onClick={() => set({ where: "all", brand: "", platform: "", theme: "", type: "", reply: "", urgency: "" })}
              className="text-[11px] text-stamp hover:underline"
            >
              Clear {active}
            </button>
          )}
        </div>
        {listView && (
          <Pick label="Reply status" value={f.reply ?? ""} onChange={(v) => set({ reply: v })} all="Any reply status" counts={count("reply")}
            options={REPLY_STATES.map((r) => [r, REPLY_LABEL[r]])} />
        )}
        {listView && (
          <Pick label="Tag" value={f.type ?? ""} onChange={(v) => set({ type: v })} all="All tags" counts={count("type")}
            options={[["complaint", "Complaint"], ["question", "Question"], ["purchase_intent", "Buyer"]]} />
        )}
        {listView && (
          <Pick label="Urgency" value={f.urgency ?? ""} onChange={(v) => set({ urgency: v })} all="Any urgency" counts={count("urgency")}
            options={[["high", "High"], ["medium", "Medium"], ["low", "Low"]]} />
        )}
        <Pick label="Client" value={f.brand} onChange={(v) => set({ brand: v, theme: "" })} all="All clients" counts={count("brand")}
          options={brands.map((b) => [b.id, b.name])} />
        {listView && issueOptions.length > 0 && (
          <Pick label="Issue" value={f.theme} onChange={(v) => set({ theme: v })} all="All issues" counts={count("theme")}
            options={issueOptions} hideEmpty />
        )}
        <Pick label="Platform" value={f.platform} onChange={(v) => set({ platform: v })} all="All platforms" counts={count("platform")}
          options={platforms.map((p) => [p, PLATFORM_LABEL[p] ?? p])} />
        <Pick label="Where" value={f.where} onChange={(v) => set({ where: v as Where })} all="Everywhere" allValue="all" counts={count("where")}
          options={[["owned", "Brand's own posts"], ["earned", "Other people's posts"]]} />
        {f.view !== "pipeline" && listView && (
          <Pick label="Sort" value={f.sort} onChange={(v) => set({ sort: v as Sort })}
            options={[["newest", "Newest first"], ["oldest", "Oldest first"], ["priority", "Highest priority"]]} />
        )}
      </div>

      <div className="mt-auto space-y-3 border-t pt-3">
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="ghost" className="h-auto w-full justify-start px-2 py-2 text-left">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
                {name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")
                  .slice(0, 2)}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">{name}</span>
                <span className="block truncate text-[10px] text-muted-foreground">{role}</span>
                <span
                  className={cn(
                    "block text-[10px]",
                    available ? "text-replied" : "text-muted-foreground",
                  )}
                >
                  {available ? "Available" : "Offline"}
                </span>
              </span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Workspace identity</DialogTitle>
            </DialogHeader>
            <label className="space-y-1 text-sm">
              Name
              <input
                className="block w-full rounded-sm border bg-card p-2"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  localStorage.setItem("overheard:name", e.target.value);
                }}
              />
            </label>
            <label className="space-y-1 text-sm">
              Role
              <input
                className="block w-full rounded-sm border bg-card p-2"
                value={role}
                onChange={(e) => {
                  setRole(e.target.value);
                  localStorage.setItem("overheard:role", e.target.value);
                }}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={available}
                onChange={(e) => setAvailable(e.target.checked)}
              />
              Available
            </label>
            <p className="text-xs text-muted-foreground">Local workspace identity</p>
          </DialogContent>
        </Dialog>
        <div className="flex items-center justify-between px-2 text-xs text-muted-foreground">
          <button
            onClick={() => setDark((d) => !d)}
            className="flex items-center gap-1 hover:text-foreground"
          >
            {dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}{" "}
            {dark ? "Light" : "Dark"}
          </button>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm" className="h-auto px-0 text-xs">
                Integrations
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif">Integrations</DialogTitle>
              </DialogHeader>
              <div className="divide-y">
                {["YouTube", "Instagram", "X", "Reddit"].map((channel) => (
                  <div key={channel} className="py-3 text-sm">
                    <span>{channel}</span>
                  </div>
                ))}
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </nav>
  );
}

const PLATFORM_ORDER = ["youtube", "instagram", "tiktok", "x", "reddit"];
const PLATFORM_LABEL: Record<string, string> = { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok", x: "X", reddit: "Reddit" };

function Pick({
  label,
  value,
  onChange,
  options,
  all,
  allValue = "",
  counts,
  hideEmpty,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  all?: string;
  allValue?: string;
  counts?: Record<string, number> | undefined;
  hideEmpty?: boolean;
}) {
  const n = (v: string) => (counts ? ` (${counts[v] ?? 0})` : "");
  const shown = hideEmpty && counts ? options.filter(([v]) => (counts[v] ?? 0) > 0 || v === value) : options;
  return (
    <label className="block space-y-1">
      <Label>{label}</Label>
      <select
        aria-label={`Filter by ${label.toLowerCase()}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full rounded-sm border bg-card px-2 py-1 text-sm",
          all !== undefined && value !== allValue && "border-stamp/60 font-medium",
        )}
      >
        {all !== undefined && <option value={allValue}>{all}{n(allValue)}</option>}
        {shown.map(([v, text]) => (
          <option key={v} value={v}>{text}{n(v)}</option>
        ))}
      </select>
    </label>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
      {children}
    </div>
  );
}

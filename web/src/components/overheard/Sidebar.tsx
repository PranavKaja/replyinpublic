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
  const [name, setName] = useState("Alex Rivera");
  const [role, setRole] = useState("Senior Triage Lead");
  const [available, setAvailable] = useState(true);
  useEffect(() => {
    setName(localStorage.getItem("overheard:name") ?? "Alex Rivera");
    setRole(localStorage.getItem("overheard:role") ?? "Senior Triage Lead");
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

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

      <div className="space-y-3 px-2">
        <Label>Where</Label>
        <select
          value={f.where}
          onChange={(e) => set({ where: e.target.value as Where })}
          className="w-full rounded-sm border bg-card px-2 py-1 text-sm"
        >
          <option value="all">Everywhere</option>
          <option value="owned">Brand's own posts</option>
          <option value="earned">Other people's posts</option>
        </select>
        <Label>Client</Label>
        <select
          value={f.brand}
          onChange={(e) => set({ brand: e.target.value })}
          className="w-full rounded-sm border bg-card px-2 py-1 text-sm"
        >
          <option value="">All clients</option>
          {brands.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        <Label>Platform</Label>
        <select
          value={f.platform}
          onChange={(e) => set({ platform: e.target.value })}
          className="w-full rounded-sm border bg-card px-2 py-1 text-sm"
        >
          <option value="">All platforms</option>
          <option value="youtube">YouTube</option>
          <option value="instagram">Instagram</option>
          <option value="x">X</option>
          <option value="reddit">Reddit</option>
        </select>
        {(VIEWS.some((view) => view.id === f.view) || f.view === "pipeline") && <>
          <Label>Tag</Label>
          <select
            aria-label="Filter by tag"
            value={f.type ?? ""}
            onChange={(e) => set({ type: e.target.value })}
            className="w-full rounded-sm border bg-card px-2 py-1 text-sm"
          >
            <option value="">All tags</option>
            <option value="purchase_intent">Buyer</option>
            <option value="complaint">Complaint</option>
            <option value="question">Question</option>
            <option value="praise">Praise</option>
            <option value="noise">Noise</option>
          </select>
        </>}
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

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
      {children}
    </div>
  );
}

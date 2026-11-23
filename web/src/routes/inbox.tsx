import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Menu, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { dataQuery, useSetStatus, SignedOut, useSetStatusMany } from "@/lib/overheard/data";
import {
  effectiveStatus,
  filterMentions,
  inboxCount,
  isFeedback,
  type Filters,
  type Mention,
  type Sort,
  type Status,
  type View,
  type Where,
  matches,
  REPLY_STATES,
} from "@/lib/overheard/logic";
import { BrandKitView } from "@/components/overheard/BrandKitView";
import { LoadingIntro } from "@/components/overheard/LoadingIntro";
import { Logo } from "@/components/overheard/Logo";
import { Sidebar } from "@/components/overheard/Sidebar";
import { MentionList } from "@/components/overheard/MentionList";
import { Reader, copyDraft } from "@/components/overheard/Reader";
import {
  BrandsView,
  IssuesView,
  MetricsView,
  PipelineView,
} from "@/components/overheard/Overviews";

export interface Search {
  view?: View | undefined;
  where?: Where | undefined;
  brand?: string | undefined;
  platform?: string | undefined;
  theme?: string | undefined;
  type?: string | undefined;
  reply?: string | undefined;
  urgency?: string | undefined;
  q?: string | undefined;
  sort?: Sort | undefined;
  id?: string | undefined;
}
type RawSearch = { [K in keyof Search]?: unknown };
const VIEWS: View[] = [
  "inbox",
  "parked",
  "snoozed",
  "handled",
  "feedback",
  "pipeline",
  "issues",
  "brands",
  "metrics",
  "kit",
];
const str = (v: unknown) => (typeof v === "string" && v ? v : undefined);

export const Route = createFileRoute("/inbox")({
  validateSearch: (raw: Record<string, unknown>): Search => {
    const s = raw as RawSearch;
    return {
      view: VIEWS.includes(s.view as View) ? (s.view as View) : undefined,
      where: s.where === "owned" || s.where === "earned" ? s.where : undefined,
      brand: str(s.brand),
      platform: str(s.platform),
      theme: str(s.theme),
      type: ["purchase_intent", "complaint", "question", "feedback"].includes(s.type as string) ? str(s.type) : undefined,
      reply: (REPLY_STATES as string[]).includes(s.reply as string) ? str(s.reply) : undefined,
      urgency: ["high", "medium", "low"].includes(s.urgency as string) ? str(s.urgency) : undefined,
      q: str(s.q),
      sort: ["oldest", "priority"].includes(s.sort as string) ? (s.sort as Sort) : undefined,
      id: str(s.id),
    };
  },
  head: () => ({
    meta: [
      { title: "Inbox | ReplyInPublic" },
      { name: "robots", content: "noindex, follow" },
      { name: "description", content: "Sign in to read public customer comments in the ReplyInPublic inbox." },
    ],
  }),
  loader: async ({ context }) => {
    try {
      return await context.queryClient.ensureQueryData(dataQuery);
    } catch (error) {
      if (error instanceof SignedOut) throw redirect({ to: "/login" });
      throw error;
    }
  },
  component: App,
  errorComponent: ({ error }) => (
    <div className="p-10 font-serif text-xl">
      Could not load the inbox. {error instanceof Error ? error.message : ""}
    </div>
  ),
  notFoundComponent: () => <div className="p-10">Not found.</div>,
});

const TITLES: Record<string, string> = {
  inbox: "Inbox",
  parked: "Parked for reply",
  snoozed: "Snoozed",
  handled: "Handled",
  feedback: "Feedback for brand",
};

function App() {
  const { data, refetch, isFetching, dataUpdatedAt } = useSuspenseQuery(dataQuery);
  const s = Route.useSearch();
  const navigate = useNavigate({ from: "/inbox" });
  const f: Filters = {
    view: s.view ?? "inbox",
    where: s.where ?? "all",
    brand: s.brand ?? "",
    platform: s.platform ?? "",
    theme: s.theme ?? "",
    type: s.type ?? "",
    reply: s.reply ?? "",
    urgency: s.urgency ?? "",
    q: s.q ?? "",
    sort: s.sort ?? "newest",
  };
  const set = useCallback(
    (p: Partial<Filters> & { id?: string }) => {
      navigate({
        search: (prev) => {
          const next: Record<string, unknown> = { ...prev, ...p };
          for (const k of Object.keys(next))
            if (
              next[k] === "" ||
              next[k] === "all" ||
              next[k] === "newest" ||
              (k === "view" && next[k] === "inbox")
            )
              delete next[k];
          return next as Search;
        },
        replace: true,
      });
    },
    [navigate],
  );

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  const [q, setQ] = useState(f.q);
  useEffect(() => {
    const t = setTimeout(() => q !== f.q && set({ q }), 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const brands = useMemo(() => new Map(data.brands.map((b) => [b.id, b])), [data.brands]);
  const graceOf = useCallback((id: string) => brands.get(id)?.grace_hours ?? 24, [brands]);
  const items = useMemo(
    () => filterMentions(data.mentions, { ...f, q }, now, graceOf),
    [data.mentions, f.view, f.where, f.brand, f.platform, f.theme, f.type, f.reply, f.urgency, f.sort, q, now, graceOf],
  ); // eslint-disable-line react-hooks/exhaustive-deps
  const counts = useMemo(() => {
    const c: Record<string, number> = { inbox: inboxCount(data.mentions, now) };
    for (const m of data.mentions) {
      const st = effectiveStatus(m, now);
      if (st !== "inbox" && st !== "feedback") c[st] = (c[st] ?? 0) + 1;
      if (isFeedback(m)) c["feedback"] = (c["feedback"] ?? 0) + 1;
    }
    return c;
  }, [data.mentions, now]);

  const selectedId =
    s.id && data.mentions.some((m) => m.id === s.id) ? s.id : (items[0]?.id ?? null);
  const selected = data.mentions.find((m) => m.id === selectedId) ?? null;
  const [mobileReader, setMobileReader] = useState(false);
  const [menu, setMenu] = useState(false);
  const [leaving, setLeaving] = useState<string | null>(null);
  const setStatus = useSetStatus();
  const lastUndo = useRef<(() => void) | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const select = (id: string) => {
    set({ id });
    setMobileReader(true);
  };

  const change = useCallback(
    (m: Mention, status: Status, advance = true) => {
      const prev = { status: m.status as Status, snoozed_until: m.snoozed_until, is_feedback: m.is_feedback ?? false };
      // Feedback on an already handled message just tags it; from the queue it also moves it out.
      const tagOnly = status === "feedback" && m.status === "handled";
      if (status === "feedback" && tagOnly) {
        setStatus.mutate({ id: m.id, status: m.status as Status, snoozed_until: m.snoozed_until, is_feedback: true });
        const undo = () => setStatus.mutate({ id: m.id, ...prev });
        lastUndo.current = undo;
        toast("Also saved as feedback for brand", { duration: 5000, action: { label: "Undo", onClick: undo } });
        return;
      }
      const idx = items.findIndex((x) => x.id === m.id);
      const next = items[idx + 1] ?? items[idx - 1];
      const snoozed_until =
        status === "snoozed" ? new Date(Date.now() + 86_400_000).toISOString() : null;
      setLeaving(m.id);
      setTimeout(() => {
        setStatus.mutate({ id: m.id, status, snoozed_until, ...(status === "feedback" ? { is_feedback: true } : {}) });
        setLeaving(null);
        if (advance) set({ id: next && next.id !== m.id ? next.id : "" });
      }, 200);
      const undo = () => {
        setStatus.mutate({ id: m.id, ...prev });
        set({ id: m.id });
        lastUndo.current = null;
      };
      lastUndo.current = undo;
      const label: Record<Status, string> = {
        handled: "Marked handled",
        parked: "Parked for reply",
        snoozed: "Snoozed for 24h",
        dismissed: "Marked not ours",
        feedback: "Moved to feedback for brand",
        inbox: "Moved to inbox",
      };
      toast(label[status], { duration: 5000, action: { label: "Undo", onClick: undo } });
    },
    [items, set, setStatus],
  );

  const setMany = useSetStatusMany();
  // Everything in the open message's issue that sits in the same place as it does right now.
  const issueGroup = useMemo(() => {
    if (!selected?.theme_id) return [];
    const here = effectiveStatus(selected, now);
    return data.mentions.filter(
      (m) => m.theme_id === selected.theme_id && effectiveStatus(m, now) === here,
    );
  }, [data.mentions, selected, now]);
  const moveIssue = useCallback(
    (status: Status) => {
      const group = issueGroup.filter((m) => m.status !== status);
      if (!group.length) return;
      const moved = new Set(group.map((m) => m.id));
      const before = group.map((m) => ({
        id: m.id,
        status: m.status as Status,
        snoozed_until: m.snoozed_until,
        is_feedback: m.is_feedback ?? false,
      }));
      const snoozed_until =
        status === "snoozed" ? new Date(Date.now() + 86_400_000).toISOString() : null;
      const keep = selected?.id ?? "";
      const next = items.find((x) => !moved.has(x.id));
      setMany.mutate(
        group.map((m) => ({
          id: m.id,
          status,
          snoozed_until,
          ...(status === "feedback" ? { is_feedback: true } : {}),
        })),
      );
      set({ id: next?.id ?? "" });
      const undo = () => {
        setMany.mutate(before);
        set({ id: keep });
        lastUndo.current = null;
      };
      lastUndo.current = undo;
      const where: Record<Status, string> = {
        handled: "marked handled",
        parked: "parked for reply",
        snoozed: "snoozed for 24h",
        dismissed: "marked not ours",
        feedback: "moved to feedback for brand",
        inbox: "moved to inbox",
      };
      toast(`${group.length} ${group.length === 1 ? "message" : "messages"} ${where[status]}`, {
        duration: 10000,
        action: { label: "Undo", onClick: undo },
      });
    },
    [issueGroup, items, selected, set, setMany],
  );

  const act = (st: Status) => selected && change(selected, st);
  const isList = f.view in TITLES;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey)
        return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (e.key === "u") {
        lastUndo.current?.();
        return;
      }
      if (!isList) return;
      const i = items.findIndex((m) => m.id === selectedId);
      const nx = items[i + 1],
        pv = items[i - 1];
      if (e.key === "j" && nx) set({ id: nx.id });
      else if (e.key === "k" && pv) set({ id: pv.id });
      else if (!selected) return;
      else if (e.key === "e") act("handled");
      else if (e.key === "s") act("snoozed");
      else if (e.key === "x") act("dismissed");
      else if (e.key === "p") act("parked");
      else if (e.key === "f") act("feedback");
      else if (e.key === "c" && selected.draft) copyDraft(selected.draft);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const sidebar = (
    <Sidebar
      f={f}
      set={(p) => {
        set({ ...p, id: "" });
        setMenu(false);
      }}
      brands={data.brands}
      themes={data.themes}
      mentions={data.mentions}
      counts={counts}
      me={data.me}
    />
  );
  const openSibling = (id: string) => {
    if (items.some((m) => m.id === id)) return set({ id });
    const m = data.mentions.find((x) => x.id === id);
    const st = m ? effectiveStatus(m, now) : "inbox";
    const view = (VIEWS as string[]).includes(st) ? (st as View) : "inbox";
    setQ("");
    set({ id, view, brand: "", platform: "", theme: "", type: "", reply: "", urgency: "", where: "all", q: "" });
  };
  const theme = selected?.theme_id
    ? data.themes.find((t) => t.id === selected.theme_id)
    : undefined;
  const reader = (
    <Reader
      m={selected}
      brand={selected ? brands.get(selected.brand_id) : undefined}
      theme={theme}
      siblings={
        theme ? data.mentions.filter((m) => m.theme_id === theme.id && m.id !== selected?.id) : []
      }
      act={act}
      onSelect={openSibling}
      moveIssue={moveIssue}
      issueCount={issueGroup.length}
    />
  );
  const openMention = (id: string) => {
    const m = data.mentions.find((x) => x.id === id);
    if (!m) return;
    const st = effectiveStatus(m, now);
    set({ view: (st === "dismissed" ? "inbox" : st) as View, id });
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <LoadingIntro />
      <aside className="hidden w-[220px] shrink-0 border-r md:block">{sidebar}</aside>
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetContent side="left" className="w-[260px] p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          {sidebar}
        </SheetContent>
      </Sheet>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b px-3 py-2 md:hidden">
          <button onClick={() => setMenu(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <Logo />
        </div>
        <div className="flex items-center justify-end gap-2 border-b px-4 py-1.5 text-xs text-muted-foreground">
          <span>
            {isFetching
              ? "Refreshing…"
              : `Updated ${Math.max(0, Math.floor((now - dataUpdatedAt) / 60_000))} min ago`}
          </span>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            title="Refresh messages"
            aria-label="Refresh messages"
            disabled={isFetching}
            onClick={() => {
              void refetch().then((result) => {
                if (result.isError) toast.error("Refresh failed");
                else setNow(Date.now());
              });
            }}
          >
            <RefreshCw className={isFetching ? "animate-spin" : ""} />
          </Button>
        </div>
        <div className="flex min-h-0 flex-1">
          {isList ? (
            <>
              <div className="w-full min-w-0 border-r md:w-[380px] md:shrink-0">
                <MentionList
                  ref={searchRef}
                  items={items}
                  brands={brands}
                  selected={selectedId}
                  onSelect={select}
                  f={f}
                  set={set}
                  q={q}
                  setQ={setQ}
                  leaving={leaving}
                  title={
                    f.theme
                      ? (data.themes.find((t) => t.id === f.theme)?.name ?? "Inbox")
                      : (TITLES[f.view] ?? "Inbox")
                  }
                />
              </div>
              <div className="hidden min-w-0 flex-1 md:block">{reader}</div>
              {mobileReader && selected && (
                <div className="fixed inset-0 z-40 bg-background md:hidden">
                  <Reader
                    m={selected}
                    brand={brands.get(selected.brand_id)}
                    theme={theme}
                    siblings={
                      theme
                        ? data.mentions.filter(
                            (m) => m.theme_id === theme.id && m.id !== selected.id,
                          )
                        : []
                    }
                    act={(st) => {
                      act(st);
                      setMobileReader(false);
                    }}
                    onSelect={openSibling}
                    moveIssue={moveIssue}
                    issueCount={issueGroup.length}
                    onBack={() => setMobileReader(false)}
                  />
                </div>
              )}
            </>
          ) : (
            <div className="min-w-0 flex-1">
              {f.view === "issues" && (
                <IssuesView
                  themes={data.themes}
                  brands={data.brands.filter((b) => !f.brand || b.id === f.brand)}
                  mentions={data.mentions}
                  open={(t) => set({ view: "inbox", theme: t, id: "" })}
                />
              )}
              {f.view === "brands" && (
                <BrandsView
                  brands={data.brands}
                  mentions={data.mentions}
                  pick={(b) => set({ view: "inbox", brand: b, id: "" })}
                />
              )}
              {f.view === "metrics" && (
                <MetricsView
                  mentions={data.mentions.filter((m) => !f.brand || m.brand_id === f.brand)}
                  brands={data.brands}
                />
              )}
              {f.view === "kit" && (
                <BrandKitView
                  brands={data.brands}
                  current={f.brand}
                  pick={(b) => set({ brand: b })}
                />
              )}
              {f.view === "pipeline" && (
                <PipelineView
                  mentions={data.mentions.filter((m) => matches(m, { ...f, q: "" }, graceOf, now))}
                  brands={brands}
                  move={(id, st) => {
                    const m = data.mentions.find((x) => x.id === id);
                    if (m && m.status !== st) change(m, st, false);
                  }}
                  open={openMention}
                />
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

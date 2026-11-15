import { Link } from "@tanstack/react-router";
import { ArrowLeft, Copy, Heart, Eye } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InternalNotes } from "./InternalNotes";
import { cn } from "@/lib/utils";
import { compact, type Brand, type Mention, type Status, type Theme } from "@/lib/overheard/logic";
import { useSaveDraft } from "@/lib/overheard/data";
import { Highlighted, PlatformIcon, ReplyStatus, TypeBadge, rel } from "./bits";

interface Props {
  m: Mention | null;
  brand?: Brand | undefined;
  theme?: Theme | undefined;
  siblings: Mention[];
  act: (s: Status) => void;
  onSelect: (id: string) => void;
  onBack?: (() => void) | undefined;
  moveIssue?: ((status: Status) => void) | undefined;
  issueCount?: number | undefined;
}

const ISSUE_MOVES: [Status, string][] = [
  ["feedback", "Feedback"],
  ["parked", "Parked"],
  ["snoozed", "Snoozed"],
  ["handled", "Handled"],
  ["inbox", "Inbox"],
];

export function Reader({ m, brand, theme, siblings, act, onSelect, onBack, moveIssue, issueCount = 0 }: Props) {
  if (!m)
    return (
      <div className="flex h-full items-center justify-center font-serif text-xl font-semibold tracking-tight text-muted-foreground">
        Pick a message to read.
      </div>
    );
  const where =
    m.surface === "owned"
      ? "on their own post"
      : `under ${m.parent_author}'s ${m.platform === "youtube" ? "video" : "post"}: ${m.parent_title}`;
  return (
    <article className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 md:px-10">
        {onBack && (
          <button
            onClick={onBack}
            className="mb-4 flex items-center gap-1 text-sm text-muted-foreground"
          >
            <ArrowLeft className="size-4" /> Back
          </button>
        )}
        <div className="mx-auto max-w-[640px] space-y-6">
          {/* Where it was said: small and quiet, so the message below is the first thing read. */}
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold">{brand?.name}</span>
              <PlatformIcon p={m.platform} />
              <span className="text-muted-foreground">{where}</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-muted-foreground">
              <span>
                {new Date(m.posted_at).toLocaleString("en-US", {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                  timeZone: "UTC",
                })}{" "}
                UTC
              </span>
              <span>{rel(m.posted_at)}</span>
              {m.like_count > 0 && (
                <span className="flex items-center gap-1">
                  <Heart className="size-3" />
                  {m.like_count}
                </span>
              )}
              {m.view_count > 0 && (
                <span className="flex items-center gap-1">
                  <Eye className="size-3" />
                  {compact(m.view_count)} views on thread
                </span>
              )}
            </div>
          </div>

          {/* The customer's own words: the one boxed, large block on the page. */}
          <figure className="overflow-hidden rounded-lg border border-l-4 border-l-stamp bg-slip shadow-[0_1px_2px_color-mix(in_oklab,var(--foreground)_8%,transparent)]">
            <figcaption className="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-4 py-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                Customer message
              </span>
              <span className="text-sm font-medium">@{m.author}</span>
              <span className="ml-auto flex items-center gap-2">
                <TypeBadge type={m.type} />
                <ReplyStatus m={m} grace={brand?.grace_hours ?? 24} />
              </span>
            </figcaption>
            <blockquote className="whitespace-pre-wrap break-words px-4 py-4 text-xl font-medium leading-8 text-foreground">
              {m.text}
            </blockquote>
            <div className="flex flex-wrap items-center gap-3 border-t px-4 py-2 text-xs">
              <span className={cn(m.proof === "api" || m.proof === "human" ? "text-replied" : "text-amber")}>
                {m.proof === "api" || m.proof === "human" ? "Verified" : "Unverified"}
              </span>
              <a
                href={m.url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto text-primary underline underline-offset-2"
              >
                Open original
              </a>
            </div>
          </figure>

          {theme && (
            <div className="space-y-2">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                Same issue
              </div>
              <div className="font-serif text-lg">
                {theme.name}{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  {siblings.length + 1} messages
                </span>
              </div>
              {moveIssue && issueCount > 1 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-muted-foreground">Move all {issueCount} here to</span>
                  {ISSUE_MOVES.filter(([st]) => st !== m.status).map(([st, label]) => (
                    <button
                      key={st}
                      onClick={() => moveIssue(st)}
                      className="rounded-sm border px-2 py-1 font-medium hover:bg-accent/60"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              <ul className="max-h-64 divide-y overflow-y-auto overscroll-contain rounded-sm border">
                {siblings.map((s) => (
                  <li key={s.id}>
                    <button
                      onClick={() => onSelect(s.id)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent/50"
                    >
                      <PlatformIcon p={s.platform} />
                      <span className="w-24 shrink-0 truncate text-muted-foreground">
                        @{s.author}
                      </span>
                      <span className="truncate">{s.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Tabs key={m.id} defaultValue={m.draft !== null ? "reply" : "notes"}>
            <TabsList>
              {m.draft !== null && <TabsTrigger value="reply">Suggested reply</TabsTrigger>}
              <TabsTrigger value="notes">Internal notes</TabsTrigger>
            </TabsList>
            {m.draft !== null && (
              <TabsContent value="reply">
                <Draft m={m} />
              </TabsContent>
            )}
            <TabsContent value="notes">
              <InternalNotes id={m.id} />
            </TabsContent>
          </Tabs>
        </div>
      </div>
      <div className="sticky bottom-0 flex flex-wrap gap-2 border-t bg-background/95 px-6 py-3 md:px-10">
        <Button onClick={() => act("handled")}>
          Mark handled <Kbd>e</Kbd>
        </Button>
        <Button variant="outline" onClick={() => act("parked")}>
          Park for reply <Kbd>p</Kbd>
        </Button>
        <Button variant="outline" onClick={() => act("snoozed")}>
          Snooze 24h <Kbd>s</Kbd>
        </Button>
        <Button variant="ghost" onClick={() => act("feedback")}>
          Feedback for brand <Kbd>f</Kbd>
        </Button>
        <Button variant="ghost" onClick={() => act("dismissed")}>
          Not ours <Kbd>x</Kbd>
        </Button>
      </div>
    </article>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="ml-1 hidden rounded-sm border border-current/30 px-1 font-mono text-[10px] opacity-60 lg:pointer-fine:inline">
      {children}
    </kbd>
  );
}

function Draft({ m }: { m: Mention }) {
  const [text, setText] = useState(m.draft ?? "");
  const save = useSaveDraft();
  const t = useRef<ReturnType<typeof setTimeout>>(undefined);
  const commit = () => {
    if (text !== m.draft) save.mutate({ id: m.id, draft: text });
  };
  useEffect(() => {
    clearTimeout(t.current);
    t.current = setTimeout(commit, 2000);
    return () => clearTimeout(t.current);
  }); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-2" data-draft={text}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Suggested reply
        </div>
        <div className="flex items-center gap-2">
        <Link
          to="/inbox"
          search={{ view: "kit", brand: m.brand_id }}
          className="text-xs text-primary underline underline-offset-2"
        >
          Brand kit
        </Link>
        <Button size="sm" variant="outline" onClick={() => copyDraft(text)}>
          <Copy className="size-3.5" /> Copy <Kbd>c</Kbd>
        </Button>
        </div>
      </div>
      <div className="relative rounded-sm border bg-card">
        <div
          aria-hidden
          className="pointer-events-none whitespace-pre-wrap break-words p-3 text-sm leading-relaxed text-transparent [&_mark]:text-transparent"
        >
          <Highlighted text={text + " "} />
        </div>
        <textarea
          aria-label="Suggested reply draft"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          className="absolute inset-0 resize-none bg-transparent p-3 text-sm leading-relaxed outline-none"
        />
      </div>
    </div>
  );
}

export function copyDraft(text: string) {
  void navigator.clipboard?.writeText(text);
  toast("Draft copied");
}

import { Search, StickyNote } from "lucide-react";
import { forwardRef, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import {
  type Brand,
  type Filters,
  type Mention,
} from "@/lib/overheard/logic";
import { PlatformIcon, ReplyStatus, TypeBadge, rel } from "./bits";
import { useHasInternalNote } from "@/lib/overheard/notes";

function NoteIndicator({ id }: { id: string }) {
  const hasNote = useHasInternalNote(id);
  if (!hasNote) return null;
  return <span title="Has internal note" aria-label="Has internal note" className="inline-flex shrink-0 items-center text-muted-foreground"><StickyNote className="size-3.5" aria-hidden="true" /></span>;
}

interface Props {
  items: Mention[];
  brands: Map<string, Brand>;
  selected: string | null;
  onSelect: (id: string) => void;
  f: Filters;
  set: (p: Partial<Filters>) => void;
  q: string;
  setQ: (q: string) => void;
  leaving: string | null;
  title: string;
}

export const MentionList = forwardRef<HTMLInputElement, Props>(function MentionList(
  { items, brands, selected, onSelect, f, set, q, setQ, leaving, title },
  ref,
) {
  const muted = f.view === "inbox";
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!selected) return;
    const id = requestAnimationFrame(() => {
      const list = listRef.current;
      const el = list?.querySelector<HTMLElement>(`[data-id="${CSS.escape(selected)}"]`);
      if (!list || !el) return;
      const top = el.offsetTop - list.offsetTop;
      if (top < list.scrollTop || top + el.offsetHeight > list.scrollTop + list.clientHeight)
        list.scrollTo({ top: top - list.clientHeight / 3, behavior: "smooth" });
    });
    return () => cancelAnimationFrame(id);
  }, [selected, items]);
  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="space-y-2 border-b px-4 pb-3 pt-4">
        <div className="flex items-baseline justify-between">
          <h1 className="font-serif text-2xl">{title}</h1>
          <span className="font-mono text-xs text-muted-foreground">{items.length}</span>
        </div>
        <div className="flex gap-2">
          <label className="flex flex-1 items-center gap-2 rounded-sm border bg-card px-2">
            <Search className="size-3.5 text-muted-foreground" />
            <input
              ref={ref}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search messages..."
              className="w-full bg-transparent py-1.5 text-sm outline-none"
            />
          </label>
        </div>
      </header>
      <ul ref={listRef} className="min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 && (
          <li className="p-8 text-center font-serif text-lg font-semibold tracking-tight text-muted-foreground">
            {q || f.brand || f.platform || f.theme || f.type || f.reply || f.urgency || f.where !== "all"
              ? "No matching messages"
              : f.view === "inbox"
                ? "Inbox Zero · All messages have been triaged"
                : "No messages"}
          </li>
        )}
        {items.map((m, i) => {
          const b = brands.get(m.brand_id);
          return (
            <li key={m.id} className={cn(leaving === m.id && "animate-slip-out")}>
              <button
                onClick={() => onSelect(m.id)}
                data-id={m.id}
                className={cn(
                  "flex w-full gap-3 border-b border-l-[3px] px-3 py-2.5 text-left transition-colors hover:bg-accent/50",
                  selected === m.id ? "border-l-stamp bg-accent/60" : "border-l-transparent",
                  muted && m.status !== "inbox" && "opacity-50",
                )}
              >
                <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <TypeBadge type={m.type} />
                    <span className="ml-auto truncate font-medium text-foreground">{b?.name}</span>
                    <PlatformIcon p={m.platform} />
                    <span
                      className={cn(
                        "rounded-sm px-1",
                        m.surface === "earned" ? "bg-buyer-soft text-buyer" : "bg-muted",
                      )}
                    >
                      {m.surface}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm font-medium leading-snug text-foreground">{m.text}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {rel(m.posted_at)}
                    </span>
                    <ReplyStatus m={m} grace={b?.grace_hours ?? 24} />
                    <NoteIndicator id={m.id} />
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
});

import { Youtube, Instagram, Twitter, MessageCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { hoursSince, isOverdue, PLACEHOLDER_RE, type Mention } from "@/lib/overheard/logic";

export function PlatformIcon({ p, className }: { p: string; className?: string }) {
  const I = p === "youtube" ? Youtube : p === "instagram" ? Instagram : p === "x" ? Twitter : MessageCircle;
  return <I aria-label={p} className={cn("size-3.5 shrink-0", className)} />;
}

export function PriorityPill({ value }: { value: number }) {
  const tone = value > 60 ? "bg-stamp-soft text-stamp" : value >= 30 ? "bg-amber-soft text-amber" : "bg-muted text-muted-foreground";
  return <span className={cn("inline-flex w-9 justify-center rounded-sm py-0.5 font-mono text-xs font-semibold", tone)}>{Math.round(value)}</span>;
}

const TAG_TONE = {
  stamp: "bg-stamp-soft text-stamp",
  replied: "bg-replied-soft text-replied",
  amber: "bg-amber-soft text-amber",
  buyer: "bg-buyer-soft text-buyer",
  muted: "bg-muted text-muted-foreground",
} as const;

export function Tag({
  tone = "muted",
  className,
  children,
}: {
  tone?: keyof typeof TAG_TONE;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        TAG_TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const TYPE_LABEL: Record<string, string> = { complaint: "complaint", question: "question", purchase_intent: "buyer", praise: "praise", noise: "noise" };
export function TypeBadge({ type }: { type: string }) {
  const tone = type === "complaint" ? "border-stamp/40 text-stamp" : type === "purchase_intent" ? "border-buyer/40 text-buyer bg-buyer-soft" : "border-border text-muted-foreground";
  return <span className={cn("rounded-full border px-1.5 py-px text-[10px] font-medium uppercase tracking-wide", tone)}>{TYPE_LABEL[type] ?? type}</span>;
}

export function ReplyStatus({ m, grace }: { m: Mention; grace: number }) {
  if (m.brand_replied === true) return <Tag tone="replied">Replied</Tag>;
  if (m.brand_replied === null) return <Tag tone="amber">Not confirmed</Tag>;
  if (isOverdue(m, grace)) return <Tag tone="stamp">No reply</Tag>;
  return <Tag tone="muted">Awaiting</Tag>;
}

export function Highlighted({ text }: { text: string }) {
  return (
    <>
      {text.split(PLACEHOLDER_RE).map((part, i) =>
        /^\[[^\]]+\]$/.test(part) ? <mark key={i} className="rounded-sm bg-amber-soft text-amber">{part}</mark> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

export function rel(iso: string) {
  const h = hoursSince(iso);
  return h < 1 ? "just now" : h < 48 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`;
}

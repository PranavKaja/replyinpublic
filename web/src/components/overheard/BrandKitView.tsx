import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Brand } from "@/lib/overheard/logic";
import { KITS } from "@/lib/overheard/kits";

const H = ({ children }: { children: React.ReactNode }) => (
  <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
    {children}
  </h2>
);

export function BrandKitView({
  brands,
  current,
  pick,
}: {
  brands: Brand[];
  current: string;
  pick: (id: string) => void;
}) {
  const brand = brands.find((b) => b.id === current) ?? brands[0];
  const kit = brand ? KITS[brand.slug] : undefined;
  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-10">
      <h1 className="font-serif text-3xl">Brand kit</h1>
      <div className="mt-4 flex flex-wrap gap-2">
        {brands.map((b) => (
          <button
            key={b.id}
            onClick={() => pick(b.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm transition-colors",
              b.id === brand?.id ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            {b.name}
          </button>
        ))}
      </div>
      {!kit ? (
        <p className="mt-8 text-sm text-muted-foreground">No kit for this brand yet.</p>
      ) : (
        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          <section>
            <H>Voice</H>
            <ul className="space-y-2 text-sm">
              {kit.voice.map((v) => (
                <li key={v} className="flex items-center justify-between rounded-sm border bg-card px-3 py-2">{v}<span className="ml-2 whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">Sample, not from the brand</span></li>
              ))}
            </ul>
          </section>
          <section>
            <H>Key facts</H>
            <dl className="divide-y rounded-sm border bg-card text-sm">
              {kit.facts.map((x) => (
                <div key={x.label} className="flex justify-between gap-4 px-3 py-2">
                  <dt className="text-muted-foreground">{x.label}</dt>
                  <dd className="text-right">{x.value}<span className="ml-2 whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">Sample, not from the brand</span></dd>
                </div>
              ))}
            </dl>
          </section>
          <section>
            <H>Words to use</H>
            <div className="flex flex-wrap gap-2">
              {kit.use.map((w) => (
                <span key={w} className="rounded-full bg-accent px-2.5 py-1 text-sm">{w}</span>
              ))}
            </div>
            <div className="mt-5"><H>Words to avoid</H></div>
            <div className="flex flex-wrap gap-2">
              {kit.avoid.map((w) => (
                <span key={w} className="rounded-full border px-2.5 py-1 text-sm text-muted-foreground line-through">{w}</span>
              ))}
            </div>
          </section>
          <section>
            <H>Brand colours</H>
            <div className="flex flex-wrap gap-3">
              {kit.colors.map((c) => (
                <div key={c.name} className="w-28 overflow-hidden rounded-sm border bg-card text-xs">
                  <div className="h-14" style={{ backgroundColor: c.hex }} />
                  <div className="px-2 py-1.5">
                    <div>{c.name}</div>
                    <div className="font-mono text-muted-foreground">{c.hex}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <H>Signature emoji</H>
            <div className="flex flex-wrap gap-3">
              {kit.emoji.map((x) => (
                <div key={x.e} className="flex items-center gap-2 rounded-sm border bg-card px-3 py-2 text-sm">
                  <span className="text-2xl">{x.e}</span>
                  <span className="text-muted-foreground">{x.use}</span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <H>Files</H>
            <ul className="space-y-2">
              {kit.files.map((f) => (
                <li key={f.name} className="flex items-center gap-3 rounded-sm border bg-card px-3 py-2 text-sm">
                  <FileText className="size-4 text-muted-foreground" />
                  <span className="flex-1">{f.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">{f.type} · {f.updated}</span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">Sample file</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}

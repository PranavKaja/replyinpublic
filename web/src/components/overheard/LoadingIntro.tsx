import { useEffect, useState } from "react";
import { Logo, LogoMark } from "./Logo";

/**
 * Opening intro: the listening mark pulses at center, the wordmark
 * slides in, then the screen lifts away like a
 * curtain to reveal the dashboard.
 */
export function LoadingIntro() {
  const [gone, setGone] = useState(false);
  const [skip] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const t = setTimeout(() => setGone(true), 2300);
    return () => clearTimeout(t);
  }, []);
  if (gone || skip) return null;
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background"
      style={{ animation: "intro-curtain 0.55s cubic-bezier(0.6, 0, 0.3, 1) 1.7s forwards" }}
      aria-hidden="true"
    >
      <div className="flex max-w-full flex-col items-center gap-6 px-6 text-foreground">
        <LogoMark pulse className="size-16 sm:size-24 shrink-0" />
        <div className="max-w-full opacity-0" style={{ animation: "intro-letter 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) 0.55s forwards" }}><Logo className="w-[520px]" /></div>
      </div>
    </div>
  );
}

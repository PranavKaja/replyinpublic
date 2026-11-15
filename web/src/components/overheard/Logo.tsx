import wordmarkUrl from "@/assets/replyinpublic-wordmark.png";
const wordmark = { url: wordmarkUrl };

function arc(r: number, deg: number) {
  const a = (deg * Math.PI) / 180;
  const x = (20 - r * Math.cos(a)).toFixed(2), y1 = (20 - r * Math.sin(a)).toFixed(2), y2 = (20 + r * Math.sin(a)).toFixed(2);
  return `M${x} ${y1} A${r} ${r} 0 0 0 ${x} ${y2}`;
}

export function LogoMark({ className, pulse }: { className?: string; pulse?: boolean }) {
  const wave = (delay: number) =>
    pulse ? { animation: `intro-pulse 0.9s ease-in-out ${delay}s infinite` } : undefined;
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeLinecap="round">
        <path d={arc(17, 50)} strokeWidth="3.2" style={wave(0)} />
        <path d={arc(11, 42)} strokeWidth="3.2" style={wave(0.15)} />
        <path d={arc(5.5, 30)} strokeWidth="3.2" style={wave(0.3)} />
        <path d="M20 2.5 A17.5 17.5 0 0 1 20 37.5" strokeWidth="4.5" />
      </g>
      <path d="M20 5.2 A14.8 14.8 0 0 1 20 34.8" fill="none" className="stroke-primary" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="20" cy="20" r="2.3" fill="currentColor" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <img src={wordmark.url} width={1306} height={195} alt="ReplyInPublic" className={`block h-auto w-[180px] max-w-full mix-blend-multiply dark:invert dark:mix-blend-screen ${className ?? ""}`} />
  );
}

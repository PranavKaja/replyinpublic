import { useEffect } from "react";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { MessageCircle, Inbox, Layers, Check, Globe, CornerDownRight, Bookmark, MousePointer2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import wordmarkUrl from "@/assets/replyinpublic-wordmark.png";
const wordmark = { url: wordmarkUrl };
import inboxImageUrl from "@/assets/replyinpublic-workspace.png";
const inboxImage = { url: inboxImageUrl };
import type { Search } from "./inbox";

const description = "ReplyInPublic helps brands move money from satisfaction and feedback surveys to answering the feedback customers already post in public.";

const faqs: [string, string][] = [
  ["How is this different from a survey?", "A survey starts with a question from the brand. Public feedback starts with the customer. ReplyInPublic gives those unsolicited comments a place in the workflow, so a person can act on what people are already saying."],
  ["Is it only for comments on our own posts?", "No. The inbox includes comments on brand posts and earned conversations on creator and community posts. You can filter between the two."],
  ["Does it automatically post replies?", "No. You decide what deserves a reply. The inbox helps you review a comment, keep a draft, track a next step, and open the original conversation. ReplyInPublic does not post the reply."],
  ["What can I explore in the inbox?", "The live inbox holds real public comments for five kitchen brands: KitchenAid, Nespresso, Breville, Instant Pot, and Ninja. Comments that describe the same issue are grouped. There is a follow up pipeline and a place to keep brand feedback. Opening the inbox requires a sign in."],
  ["Where do the comments come from?", "YouTube, Instagram, TikTok, X (formerly Twitter), and Reddit. The live workspace is limited to those five brands."],
  ["Does the site list a price?", "No. ReplyInPublic does not publish a price."],
];

function FaqJsonLd() {
  useEffect(() => {
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.id = "rip-faq-jsonld";
    script.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: faqs.map(([question, answer]) => ({
        "@type": "Question",
        name: question,
        acceptedAnswer: { "@type": "Answer", text: answer },
      })),
    });
    document.head.appendChild(script);
    return () => script.remove();
  }, []);
  return null;
}

export const Route = createFileRoute("/")({
  validateSearch: (raw: Record<string, unknown>): Search => ({
    view: typeof raw['view'] === "string" && ["inbox", "parked", "snoozed", "handled", "feedback", "pipeline", "issues", "brands", "metrics", "kit"].includes(raw['view']) ? raw['view'] as Search["view"] : undefined,
    where: raw['where'] === "owned" || raw['where'] === "earned" ? raw['where'] : undefined,
    ...Object.fromEntries(["brand", "platform", "theme", "type", "q", "id"].map(key => [key, typeof raw[key] === "string" ? raw[key] : undefined])),
  }),
  beforeLoad: ({ search }) => {
    if (Object.values(search).some(Boolean)) throw redirect({ to: "/inbox", search });
  },
  head: () => ({ meta: [
    { title: "ReplyInPublic | Surveys measure satisfaction. Replies earn it." },
    { name: "description", content: description },
    { property: "og:title", content: "ReplyInPublic | Surveys measure satisfaction. Replies earn it." },
    { property: "og:description", content: description },
    { property: "og:url", content: "https://replyinpublic.us/" },
    { property: "og:image", content: "https://replyinpublic.us/og.png" },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:image", content: "https://replyinpublic.us/og.png" },
  ] }),
  component: Home,
});

function Brand() {
  return <img src={wordmark.url} width={1306} height={195} alt="ReplyInPublic" className="block h-auto w-[180px] max-w-full sm:w-[210px]" />;
}

function Home() {
  return (
    <div className="public-home saas-home min-h-screen bg-background text-foreground">
      <FaqJsonLd />
      <header className="home-nav bg-background">
        <div className="mx-auto max-w-7xl px-5 lg:px-10">
          <div className="flex h-[72px] items-center justify-between gap-5 border-b border-border md:h-[88px]">
            <Link to="/" aria-label="ReplyInPublic home" className="min-w-0 shrink"><Brand /></Link>
              <nav aria-label="Main navigation" className="hidden shrink-0 items-center gap-6 text-sm font-medium text-muted-foreground md:flex lg:gap-8">
                <a href="#product" className="whitespace-nowrap py-3 transition-colors hover:text-foreground">The product</a>
                <a href="#approach" className="whitespace-nowrap py-3 transition-colors hover:text-foreground">Why public feedback</a>
                <a href="#questions" className="py-3 transition-colors hover:text-foreground">FAQs</a>
                <a href="/answers" className="py-3 transition-colors hover:text-foreground">Answers</a>
              </nav>
          </div>
        </div>
      </header>
      <main>
        <section className="saas-opening overflow-hidden">
          <div className="mx-auto max-w-7xl px-5 pt-10 text-center lg:px-10 lg:pt-8">
            <p className="mb-4 inline-flex items-center font-mono text-xs text-home-subtle">HONEST FEEDBACK. PUBLIC TRUST.</p>
            <h1 className="home-headline mx-auto max-w-5xl text-[42px] font-medium leading-[1.12] md:text-[52px] lg:text-[56px]">Surveys measure satisfaction.<br /><span className="home-highlight">Replies earn it.</span></h1>
            <p className="mx-auto mt-4 max-w-[560px] text-base leading-7 text-home-subtle md:text-lg">Your customers already told you what they think.<br className="hidden sm:block" /> Turn the comments they left into conversations that count.</p>
            <p className="mx-auto mt-3 max-w-[640px] text-sm leading-6 text-home-subtle">ReplyInPublic is the inbox for those public comments. It groups the ones about the same issue, and a person decides what to answer. The product does not post the reply.</p>
            <div className="mt-5 flex flex-wrap items-center justify-center gap-3"><Button asChild size="lg" className="h-12 px-6"><Link to="/inbox">See the live inbox</Link></Button><Button asChild variant="outline" size="lg" className="h-12 bg-background/60 px-6"><a href="#approach">Why replies, not surveys?</a></Button></div>
            <p className="mt-3 text-xs text-home-subtle">Real public comments, behind a sign in.</p>
            <div id="product" className="product-window relative mt-8 overflow-hidden rounded-lg border border-border text-left">
              <div className="flex h-10 items-center justify-between border-b border-border bg-background px-4"><div className="flex items-center gap-1.5" aria-hidden="true"><span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" /></div><span className="font-mono text-[10px] text-muted-foreground">YOUR CONVERSATIONS, IN FOCUS</span><Globe className="size-3.5 text-muted-foreground" /></div>
              <Link to="/inbox" aria-label="Explore the inbox shown in the product preview"><img src={inboxImage.url} width={1440} height={1000} fetchPriority="high" alt="The real ReplyInPublic workspace with customer comments, issue clusters and message actions" className="block h-auto w-full" /></Link>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 py-7 text-xs text-home-subtle"><span className="flex items-center gap-2"><MessageCircle className="size-4" />Unprompted feedback</span><span className="flex items-center gap-2"><Layers className="size-4" />Recurring issues, together</span><span className="flex items-center gap-2"><Check className="size-4" />A clear next action</span></div>
          </div>
        </section>
        <section id="approach" className="border-y border-border">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 md:grid-cols-[1fr_1.3fr] lg:px-10 lg:py-24">
            <div><p className="home-eyebrow">A DIFFERENT FEEDBACK LOOP</p><h2 className="mt-5 max-w-md text-3xl font-medium leading-tight md:text-[40px]">Stop asking.<br />Start listening.<br /><span className="text-primary">Then answer.</span></h2></div>
            <div><p className="max-w-xl text-xl leading-8">Move money from satisfaction surveys to answering the feedback customers already post in public.</p><p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">Nobody was prompted. You didn’t pay to collect it. And when you answer, everyone reading sees a brand that cares.</p><div className="mt-8 grid grid-cols-3 border-t border-border pt-5 text-sm"><div><span className="block mb-2 font-mono text-xs text-primary">01</span>More honest</div><div><span className="block mb-2 font-mono text-xs text-primary">02</span>Already there</div><div><span className="block mb-2 font-mono text-xs text-primary">03</span>Visible to everyone</div></div></div>
          </div>
        </section>
        <section className="mx-auto max-w-7xl px-5 py-20 lg:px-10 lg:py-24">
          <div className="mb-12"><p className="home-eyebrow">FROM COMMENT TO CONVERSATION</p><h2 className="mt-5 max-w-2xl text-3xl font-medium leading-tight md:text-[40px]">Less noise.<br />More worth answering.</h2></div>
          <div className="grid gap-10 md:grid-cols-3">
            {[
              { icon: Inbox, title: "Find the missed conversation", text: "Questions, complaints and waiting buyers. See what needs attention across brand posts and community conversations.", label: "All conversations", detail: "Questions · Complaints · Buyers", tone: "text-buyer bg-buyer-soft" },
              { icon: Layers, title: "See the issue, not just the post", text: "Bring comments about the same issue together. One frustrated customer might be telling you what many more are thinking.", label: "Same issue", detail: "One thread. A bigger picture.", tone: "text-primary bg-stamp-soft" },
              { icon: Bookmark, title: "Give every comment a next step", text: "Park a reply, follow up later or keep useful feedback for the brand. Keep your queue clear without losing the context.", label: "Parked for reply", detail: "A conversation worth coming back to.", tone: "text-replied bg-replied-soft" },
            ].map(({ icon: Icon, title, text, label, detail, tone }) => <article key={title} className="border-t border-border pt-6">
              <div className={`mb-7 flex h-32 flex-col justify-center gap-3 rounded-lg px-6 ${tone}`}><div className="flex items-center gap-3 text-sm font-medium"><Icon className="size-5" />{label}</div><div className="flex items-center gap-3 text-xs"><CornerDownRight className="size-4" />{detail}</div></div>
              <h3 className="text-lg font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-muted-foreground">{text}</p>
            </article>)}
          </div>
        </section>
        <section id="questions" className="border-t border-border bg-home-surface">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 md:grid-cols-[1fr_1.3fr] lg:px-10"><div><p className="home-eyebrow">A FEW GOOD QUESTIONS</p><h2 className="mt-5 text-3xl font-medium">Before you dive in.</h2><p className="mt-4 max-w-sm text-sm leading-6 text-muted-foreground"><a href="/answers/faq">The same answers, on their own page.</a></p></div><Accordion type="single" collapsible>
            {faqs.map(([question, answer]) => <AccordionItem value={question} key={question}><AccordionTrigger className="py-5 text-base">{question}</AccordionTrigger><AccordionContent className="max-w-xl text-sm leading-7 text-muted-foreground">{answer}</AccordionContent></AccordionItem>)}
          </Accordion></div>
        </section>
        <section className="home-closing bg-home-ink text-home-on-ink">
          <div className="mx-auto max-w-7xl px-5 py-16 text-center lg:px-10 lg:py-20"><div className="mb-6 flex items-center justify-center gap-2 font-mono text-xs text-home-positive"><MousePointer2 className="size-4 shrink-0" />THE NEXT CONVERSATION IS ALREADY THERE.</div><h2 className="mx-auto max-w-2xl text-4xl font-medium leading-tight md:text-5xl">Don’t send another survey.<br />Answer someone.</h2>
          </div>
        </section>
      </main>
      <footer className="mx-auto max-w-7xl px-5 py-8 lg:px-10">
        <div className="flex flex-wrap items-center justify-between gap-5">
          <Brand />
          <p className="text-xs text-muted-foreground">Listen in public. Earn it in the replies.</p>
          <Button asChild variant="ghost" size="sm"><Link to="/inbox">Explore the product</Link></Button>
        </div>
        <nav aria-label="Answers" className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
          <a href="/answers/what-is-replyinpublic" className="hover:text-foreground">What is ReplyInPublic</a>
          <a href="/answers/public-comments-vs-surveys" className="hover:text-foreground">Public comments vs surveys</a>
          <a href="/answers/how-to-answer-public-comments" className="hover:text-foreground">How to answer</a>
          <a href="/answers/faq" className="hover:text-foreground">FAQ</a>
        </nav>
      </footer>
    </div>
  );
}

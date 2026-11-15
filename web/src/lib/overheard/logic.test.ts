import { describe, expect, it } from "vitest";
import {
  effectiveStatus,
  filterMentions,
  isBuyerWaiting,
  isOverdue,
  mentionsInPeriod,
  teamMetrics,
  type Mention,
} from "./logic";

const now = new Date("2026-11-11T12:00:00Z").getTime();
const base: Mention = {
  id: "a",
  brand_id: "b1",
  platform: "youtube",
  surface: "owned",
  url: "",
  parent_author: null,
  parent_title: null,
  author: "x",
  text: "hello",
  posted_at: new Date(now - 30 * 3_600_000).toISOString(),
  like_count: 0,
  view_count: 100,
  brand_replied: false,
  reply_text: null,
  proof: "api",
  type: "complaint",
  urgency: "high",
  needs_response: true,
  priority: 50,
  theme_id: null,
  draft: null,
  status: "inbox",
  snoozed_until: null,
  status_changed_at: null,
};
const f = {
  view: "inbox" as const,
  where: "all" as const,
  brand: "",
  platform: "",
  theme: "",
  q: "",
  sort: "priority" as const,
};

describe("triage rules", () => {
  it.each(["purchase_intent", "complaint", "question", "praise", "noise"])("filters %s tags while keeping newest first", (type) => {
    const list = [
      { ...base, id: "older", type, posted_at: new Date(now - 4000).toISOString() },
      { ...base, id: "other", type: "unrelated" },
      { ...base, id: "newer", type, posted_at: new Date(now - 1000).toISOString() },
    ];
    expect(filterMentions(list, { ...f, type, sort: "newest" }, now).map((m) => m.id)).toEqual(["newer", "older"]);
  });
  it("clearing the tag filter restores all message types", () => {
    const list = [base, { ...base, id: "buyer", type: "purchase_intent" }];
    expect(filterMentions(list, { ...f, type: "" }, now).map((m) => m.id)).toEqual(["a", "buyer"]);
  });
  const dated = (days: number) => ({
    ...base,
    id: String(days),
    posted_at: new Date(now - days * 86_400_000).toISOString(),
  });
  it("Today includes only messages since UTC midnight, not future messages", () => {
    expect(
      mentionsInPeriod([dated(0), dated(1), dated(-1)], "today", now).map((m) => m.id),
    ).toEqual(["0"]);
  });
  it("Last 7 days includes its boundary but excludes older messages", () => {
    expect(mentionsInPeriod([dated(7), dated(8)], "7", now).map((m) => m.id)).toEqual(["7"]);
  });
  it("Last 30 days includes its boundary but excludes older messages", () => {
    expect(mentionsInPeriod([dated(30), dated(31)], "30", now).map((m) => m.id)).toEqual(["30"]);
  });
  it("overdue only when no reply is confirmed and past the grace window", () => {
    expect(isOverdue(base, 24, now)).toBe(true);
    expect(isOverdue({ ...base, brand_replied: null }, 24, now)).toBe(false);
    expect(isOverdue(base, 48, now)).toBe(false);
  });
  it("snoozed items return to the inbox once snooze time passes", () => {
    expect(
      effectiveStatus(
        { ...base, status: "snoozed", snoozed_until: new Date(now - 1000).toISOString() },
        now,
      ),
    ).toBe("inbox");
    expect(
      effectiveStatus(
        { ...base, status: "snoozed", snoozed_until: new Date(now + 1000).toISOString() },
        now,
      ),
    ).toBe("snoozed");
  });
  it("inbox hides messages not directed at the brand", () => {
    expect(
      filterMentions([base, { ...base, id: "n", needs_response: false }], f, now).map((m) => m.id),
    ).toEqual(["a"]);
  });
  it("other people's posts filter keeps only earned surfaces", () => {
    const list = [base, { ...base, id: "e", surface: "earned" }];
    expect(filterMentions(list, { ...f, where: "earned" }, now).map((m) => m.id)).toEqual(["e"]);
  });
  it("a purchase question without a confirmed reply is a waiting buyer", () => {
    expect(isBuyerWaiting({ ...base, type: "purchase_intent", brand_replied: null })).toBe(true);
    expect(isBuyerWaiting({ ...base, type: "purchase_intent", brand_replied: true })).toBe(false);
  });
  it("unanswered reach sums views of open unanswered messages only", () => {
    const list = [base, { ...base, id: "h", status: "handled", view_count: 999 }];
    expect(teamMetrics(list, [], now).unansweredReach).toBe(100);
  });
});

import { isFeedback as _isFeedback } from "./logic";
describe("feedback for brand", () => {
  it("a handled message tagged as feedback counts as feedback", () => {
    expect(_isFeedback({ ...base, status: "handled", is_feedback: true })).toBe(true);
    expect(_isFeedback({ ...base, status: "handled", is_feedback: false })).toBe(false);
    expect(_isFeedback({ ...base, status: "feedback" })).toBe(true);
  });
});

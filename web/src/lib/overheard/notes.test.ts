// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readInternalNote, saveInternalNote } from "./notes";

describe("internal notes", () => {
  beforeEach(() => localStorage.clear());

  it("saves a note for its message and announces the update", () => {
    const listener = vi.fn();
    window.addEventListener("replyinpublic:note-changed", listener);
    saveInternalNote("message-a", "Customer wants a replacement");
    expect(readInternalNote("message-a")).toBe("Customer wants a replacement");
    expect(readInternalNote("message-b")).toBe("");
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("replyinpublic:note-changed", listener);
  });

  it("removes a note when empty or whitespace-only text is saved", () => {
    saveInternalNote("message-a", "Follow up");
    saveInternalNote("message-a", "  \n ");
    expect(readInternalNote("message-a")).toBe("");
    expect(localStorage.getItem("overheard:note:message-a")).toBeNull();
  });
});
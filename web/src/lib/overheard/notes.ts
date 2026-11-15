import { useSyncExternalStore } from "react";

const prefix = "overheard:note:";
const changedEvent = "replyinpublic:note-changed";

export function readInternalNote(id: string): string {
  return localStorage.getItem(`${prefix}${id}`) ?? "";
}

export function saveInternalNote(id: string, text: string): void {
  if (text.trim()) localStorage.setItem(`${prefix}${id}`, text);
  else localStorage.removeItem(`${prefix}${id}`);
  window.dispatchEvent(new Event(changedEvent));
}

function subscribe(listener: () => void) {
  window.addEventListener(changedEvent, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(changedEvent, listener);
    window.removeEventListener("storage", listener);
  };
}

export function useHasInternalNote(id: string): boolean {
  return useSyncExternalStore(subscribe, () => readInternalNote(id).trim().length > 0, () => false);
}
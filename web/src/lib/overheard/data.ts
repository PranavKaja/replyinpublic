import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

async function post(path: string, body: unknown) {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("Could not save");
}
const setMentionStatus = ({ data }: { data: unknown }) => post("/api/desk/status", data);
const saveMentionDraft = ({ data }: { data: unknown }) => post("/api/desk/draft", data);
import type { Brand, Mention, Status, Theme } from "./logic";

export interface Me { username: string; role: "brand" | "rip"; name: string; brands: string[] }
export class SignedOut extends Error {
  constructor() {
    super("Signed out");
  }
}
export async function signOut() {
  await fetch("/api/desk/logout", { method: "POST" });
}

export const dataQuery = queryOptions({
  queryKey: ["overheard"],
  queryFn: async () => {
    const r = await fetch("/api/desk/data");
    if (r.status === 401) throw new SignedOut();
    if (!r.ok) throw new Error("Could not load messages");
    return (await r.json()) as { me: Me; brands: Brand[]; themes: Theme[]; mentions: Mention[] };
  },
  refetchInterval: 60_000,
  retry: (count, error) => !(error instanceof SignedOut) && count < 2,
});

type Data = Awaited<ReturnType<typeof dataQuery.queryFn & {}>>;

export interface StatusChange { id: string; status: Status; snoozed_until?: string | null; is_feedback?: boolean }

export function useSetStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (c: StatusChange) => {
      await setMentionStatus({ data: c });
    },
    onMutate: async (c) => {
      await qc.cancelQueries({ queryKey: dataQuery.queryKey });
      qc.setQueryData<Data>(dataQuery.queryKey, (d) =>
        d && {
          ...d,
          mentions: d.mentions.map((m) =>
            m.id === c.id ? { ...m, status: c.status, snoozed_until: c.snoozed_until ?? null, status_changed_at: new Date().toISOString(), ...(c.is_feedback !== undefined ? { is_feedback: c.is_feedback } : {}) } : m,
          ),
        },
      );
    },
    onError: () => qc.invalidateQueries({ queryKey: dataQuery.queryKey }),
  });
}

/** Move many messages at once. The list updates straight away and one request saves it. */
export function useSetStatusMany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (changes: StatusChange[]) => {
      await post("/api/desk/status-batch", { changes });
    },
    onMutate: async (changes) => {
      await qc.cancelQueries({ queryKey: dataQuery.queryKey });
      const byId = new Map(changes.map((c) => [c.id, c]));
      const at = new Date().toISOString();
      qc.setQueryData<Data>(dataQuery.queryKey, (d) =>
        d && {
          ...d,
          mentions: d.mentions.map((m) => {
            const c = byId.get(m.id);
            return c
              ? { ...m, status: c.status, snoozed_until: c.snoozed_until ?? null, status_changed_at: at, ...(c.is_feedback !== undefined ? { is_feedback: c.is_feedback } : {}) }
              : m;
          }),
        },
      );
    },
    onError: () => qc.invalidateQueries({ queryKey: dataQuery.queryKey }),
  });
}

export function useSaveDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, draft }: { id: string; draft: string }) => {
      await saveMentionDraft({ data: { id, draft } });
    },
    onMutate: ({ id, draft }) =>
      qc.setQueryData<Data>(dataQuery.queryKey, (d) => d && { ...d, mentions: d.mentions.map((m) => (m.id === id ? { ...m, draft } : m)) }),
  });
}

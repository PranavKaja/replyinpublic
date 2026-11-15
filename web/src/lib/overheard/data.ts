import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

async function post(path: string, body: unknown) {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("Could not save");
}
const setMentionStatus = ({ data }: { data: unknown }) => post("/api/desk/status", data);
const saveMentionDraft = ({ data }: { data: unknown }) => post("/api/desk/draft", data);
import type { Brand, Mention, Status, Theme } from "./logic";

export const dataQuery = queryOptions({
  queryKey: ["overheard"],
  queryFn: async () => {
    const r = await fetch("/api/desk/data");
    if (!r.ok) throw new Error("Could not load messages");
    return (await r.json()) as { brands: Brand[]; themes: Theme[]; mentions: Mention[] };
  },
  refetchInterval: 60_000,
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

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { readInternalNote, saveInternalNote } from "@/lib/overheard/notes";

export function InternalNotes({ id }: { id: string }) {
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    setText(readInternalNote(id));
    setSaved(false);
  }, [id]);
  return (
    <div className="space-y-3">
      <textarea
        aria-label="Internal note"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setSaved(false);
        }}
        placeholder="Add an internal note…"
        className="min-h-32 w-full rounded-sm border bg-card p-3 text-sm"
      />
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground">
          {saved ? "Saved on this device" : "Private to this device"}
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            saveInternalNote(id, text);
            setSaved(true);
          }}
        >
          Save note
        </Button>
      </div>
    </div>
  );
}

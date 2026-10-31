"use client";

import { FileAudio, FileVideo, ImageIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { mediaUrl } from "@/services/api";
import type { MediaItem } from "@/types";
import { fmtBytes } from "./labels";

/** Loads a short-lived, authorized link for a private media item. */
export function MediaView({ item }: { item: MediaItem }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    mediaUrl(item.media_id).then((u) => alive && setUrl(u)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [item.media_id]);

  const meta = (
    <div className="mt-1 truncate text-xs text-slate-500">
      {item.original_filename || item.media_type.toLowerCase()} · {fmtBytes(item.file_size_bytes)}
      {item.duration_seconds ? ` · ${item.duration_seconds.toFixed(0)}s` : ""}
    </div>
  );
  if (failed) return <div className="rounded border border-slate-200 p-3 text-xs text-slate-500">This media resource is not available to your account.</div>;
  if (!url) return <div className="h-32 animate-pulse rounded bg-slate-100" />;
  return (
    <figure className="rounded border border-slate-200 bg-white p-2">
      {item.media_type === "IMAGE" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={item.original_filename || "Complaint photo"} className="h-40 w-full rounded object-cover" />
      )}
      {item.media_type === "AUDIO" && <audio controls src={url} className="w-full" />}
      {item.media_type === "VIDEO" && <video controls src={url} className="h-40 w-full rounded bg-black" />}
      <figcaption className="flex items-center gap-1">
        {item.media_type === "IMAGE" ? <ImageIcon className="h-3 w-3" /> : item.media_type === "AUDIO" ? <FileAudio className="h-3 w-3" /> : <FileVideo className="h-3 w-3" />}
        {meta}
      </figcaption>
    </figure>
  );
}

export function MediaGrid({ items }: { items: MediaItem[] }) {
  if (!items.length) return <p className="text-sm text-slate-500">No media attached.</p>;
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{items.map((m) => <MediaView key={m.media_id} item={m} />)}</div>;
}

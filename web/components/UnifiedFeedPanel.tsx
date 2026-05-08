import { formatRelativeDate, type FeedEntry } from "@/lib/api";

/** Per-lead unified timeline (VAN's "messaging hub" — but with AI
 *  voice calls + structured intake folded into the same stream).
 *
 *  Server-rendered, no live polling. The lead detail page passes in
 *  whatever the API returned at request time; refreshing the page
 *  refetches.
 *
 *  When `lastSeenInboundAt` is provided, inbound entries newer than
 *  that timestamp are highlighted as "new since you last looked" so
 *  the rep can spot replies without re-reading the whole thread.
 */
export function UnifiedFeedPanel({
  entries,
  lastSeenInboundAt = null,
}: {
  entries: FeedEntry[];
  lastSeenInboundAt?: string | null;
}) {
  const seenMs = lastSeenInboundAt
    ? new Date(lastSeenInboundAt).getTime()
    : 0;
  if (entries.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold">Activity</h2>
        </div>
        <p className="px-5 py-4 text-xs text-ink-500">
          No activity yet. Send a text or place an AI voice call to start
          the conversation.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <h2 className="text-sm font-semibold">Activity</h2>
        <span className="text-[10px] uppercase tracking-wider text-ink-500">
          {entries.length} {entries.length === 1 ? "entry" : "entries"}
        </span>
      </div>
      <ol className="divide-y divide-ink-100">
        {entries.map((e) => {
          const isInbound =
            e.direction === "inbound" || e.kind === "message:inbound";
          const isNew =
            isInbound &&
            seenMs > 0 &&
            new Date(e.created_at).getTime() > seenMs;
          return (
            <li
              key={`${e.source_table}-${e.source_id}`}
              className={`flex gap-3 px-5 py-3 ${
                isNew ? "bg-amber-50 border-l-2 border-amber-400" : ""
              }`}
            >
              <Glyph kind={e.kind} direction={e.direction} />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs font-medium text-ink-700 flex items-center gap-1.5">
                    {label(e.kind, e.direction)}
                    {isNew && (
                      <span className="badge bg-amber-200 text-amber-900 text-[9px]">
                        NEW
                      </span>
                    )}
                  </span>
                  <time className="text-[10px] tabular text-ink-500">
                    {formatRelativeDate(e.created_at)}
                  </time>
                </div>
                {e.body && (
                  <p className="mt-0.5 text-sm text-ink-800 whitespace-pre-wrap break-words">
                    {e.body}
                  </p>
                )}
                {(e.actor || e.delivery_status) && (
                  <p className="mt-0.5 text-[11px] text-ink-500 tabular">
                    {e.actor && <>by {e.actor}</>}
                    {e.actor && e.delivery_status && " · "}
                    {e.delivery_status && <>{e.delivery_status}</>}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function label(kind: string, direction: string | null): string {
  if (kind === "voice_call") return "AI voice call";
  if (kind === "message:outbound") return "Text · sent";
  if (kind === "message:inbound") return "Text · received";
  if (kind.startsWith("interaction:")) {
    const sub = kind.split(":")[1] ?? "note";
    if (sub === "status_change") return "Status change";
    if (sub === "task") return "Task";
    if (sub === "note") return "Note";
    if (sub === "call") return direction === "inbound" ? "Call · in" : "Call · out";
    if (sub === "text") return direction === "inbound" ? "Text · in" : "Text · out";
    if (sub === "email") return direction === "inbound" ? "Email · in" : "Email · out";
    return sub;
  }
  return kind;
}

function Glyph({
  kind,
  direction,
}: {
  kind: string;
  direction: string | null;
}) {
  // Color + emoji-free icon via inline SVG; ties the row visually to
  // its kind without depending on an icon library.
  const palette = paletteFor(kind, direction);
  return (
    <span
      className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${palette.bg}`}
      title={kind}
    >
      <svg
        viewBox="0 0 24 24"
        width="12"
        height="12"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={palette.fg}
        aria-hidden
      >
        <path d={palette.path} />
      </svg>
    </span>
  );
}

function paletteFor(
  kind: string,
  direction: string | null,
): { bg: string; fg: string; path: string } {
  if (kind === "voice_call") {
    return {
      bg: "bg-violet-100",
      fg: "text-violet-700",
      path: "M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z",
    };
  }
  if (kind.startsWith("message:")) {
    const inbound = kind.endsWith("inbound");
    return {
      bg: inbound ? "bg-emerald-100" : "bg-brand-100",
      fg: inbound ? "text-emerald-700" : "text-brand-700",
      path: "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
    };
  }
  if (kind === "interaction:status_change") {
    return {
      bg: "bg-amber-100",
      fg: "text-amber-700",
      path: "M3 12a9 9 0 0118 0M21 12a9 9 0 01-18 0M16 6l5-1m-2 6l3 1M5 18l-3-1m2-6l-3-1",
    };
  }
  if (kind === "interaction:task") {
    return {
      bg: "bg-sky-100",
      fg: "text-sky-700",
      path: "M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11",
    };
  }
  // notes / text / email / call default
  void direction;
  return {
    bg: "bg-ink-100",
    fg: "text-ink-700",
    path: "M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4z",
  };
}

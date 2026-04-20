import { type Interaction, type Lead, formatPrice, formatRelativeDate } from "@/lib/api";
import {
  addInteractionAction,
  claimLeadAction,
  updateLeadStatusAction,
} from "@/app/listings/[id]/actions";

const STATUSES: { value: Lead["status"]; label: string }[] = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "negotiating", label: "Negotiating" },
  { value: "appointment", label: "Appointment" },
  { value: "purchased", label: "Purchased" },
  { value: "lost", label: "Lost" },
];

const STATUS_STYLES: Record<Lead["status"], string> = {
  new: "bg-ink-100 text-ink-700",
  contacted: "bg-sky-100 text-sky-800",
  negotiating: "bg-indigo-100 text-indigo-800",
  appointment: "bg-violet-100 text-violet-800",
  purchased: "bg-emerald-100 text-emerald-800",
  lost: "bg-rose-100 text-rose-800",
};

const KIND_ICONS: Record<Interaction["kind"], string> = {
  note: "📝",
  call: "📞",
  text: "💬",
  email: "✉️",
  task: "✅",
  status_change: "🔄",
};

export function LeadPanel({
  listingId,
  lead,
  interactions,
}: {
  listingId: number;
  lead: Lead | null;
  interactions: Interaction[];
}) {
  if (!lead) {
    return (
      <div className="panel p-5">
        <h3 className="text-sm font-semibold">Claim this lead</h3>
        <p className="mt-1 text-xs text-ink-500">
          Claim the listing to track outreach, notes, and status. Duplicates the seller
          across teammates are prevented automatically.
        </p>
        <form action={claimLeadAction} className="mt-4 space-y-2">
          <input type="hidden" name="listing_id" value={listingId} />
          <label className="flex flex-col gap-1">
            <span className="label">Assign to</span>
            <input
              type="text"
              name="assigned_to"
              placeholder="Your name (optional)"
              className="input"
            />
          </label>
          <button type="submit" className="btn-primary w-full justify-center">
            Claim lead
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="panel p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-ink-500">Lead #{lead.id}</p>
            <p className="mt-0.5 text-sm font-medium">
              {lead.assigned_to ?? "Unassigned"}
            </p>
            <p className="mt-0.5 text-[11px] text-ink-500">
              Updated {formatRelativeDate(lead.updated_at)}
            </p>
          </div>
          <span className={`badge ${STATUS_STYLES[lead.status]}`}>
            {lead.status.replace("_", " ")}
          </span>
        </div>

        <form action={updateLeadStatusAction} className="mt-4 flex gap-2">
          <input type="hidden" name="lead_id" value={lead.id} />
          <input type="hidden" name="listing_id" value={listingId} />
          <select name="status" defaultValue={lead.status} className="input flex-1">
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-secondary">
            Update
          </button>
        </form>

        {lead.offered_price !== null && (
          <p className="mt-3 text-sm">
            Last offer:{" "}
            <strong className="tabular">{formatPrice(lead.offered_price)}</strong>
          </p>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h3 className="text-sm font-semibold">Log activity</h3>
        </div>
        <form action={addInteractionAction} className="space-y-2 p-4">
          <input type="hidden" name="lead_id" value={lead.id} />
          <input type="hidden" name="listing_id" value={listingId} />
          <div className="flex gap-2">
            <select name="kind" defaultValue="note" className="input w-28">
              <option value="note">Note</option>
              <option value="call">Call</option>
              <option value="text">Text</option>
              <option value="email">Email</option>
              <option value="task">Task</option>
            </select>
            <input
              name="body"
              required
              placeholder="What happened?"
              className="input flex-1"
            />
          </div>
          <button type="submit" className="btn-primary w-full justify-center">
            Log
          </button>
        </form>
      </div>

      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <h3 className="text-sm font-semibold">History</h3>
          <span className="text-[11px] text-ink-500 tabular">
            {interactions.length} event{interactions.length === 1 ? "" : "s"}
          </span>
        </div>
        {interactions.length === 0 ? (
          <p className="p-5 text-xs text-ink-500">
            No activity yet. First outreach goes furthest.
          </p>
        ) : (
          <ul className="divide-y divide-ink-200">
            {interactions.map((i) => (
              <li key={i.id} className="flex gap-3 px-5 py-3 text-sm">
                <span className="pt-0.5" aria-hidden>
                  {KIND_ICONS[i.kind] ?? "•"}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="whitespace-pre-wrap">{i.body}</p>
                  <p className="mt-0.5 text-[11px] text-ink-500">
                    {i.kind.replace("_", " ")}
                    {i.actor ? ` · ${i.actor}` : ""} · {formatRelativeDate(i.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

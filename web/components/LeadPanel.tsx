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
  new: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  contacted: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  negotiating: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300",
  appointment: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  purchased: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  lost: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
};

const INTERACTION_ICONS: Record<Interaction["kind"], string> = {
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
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <h2 className="text-sm font-semibold">Work this lead</h2>
        <p className="mt-1 text-sm text-slate-500">
          Claim this listing to start tracking your outreach and notes.
        </p>
        <form action={claimLeadAction} className="mt-3 flex flex-wrap gap-2">
          <input type="hidden" name="listing_id" value={listingId} />
          <input
            type="text"
            name="assigned_to"
            placeholder="Assign to (optional)"
            className="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            className="rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Claim lead
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Lead #{lead.id}</h2>
            <p className="text-xs text-slate-500">
              Owned by <strong>{lead.assigned_to ?? "unassigned"}</strong> ·
              updated {formatRelativeDate(lead.updated_at)}
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_STYLES[lead.status]}`}>
            {lead.status.replace("_", " ")}
          </span>
        </div>

        <form action={updateLeadStatusAction} className="mt-3 flex flex-wrap gap-2">
          <input type="hidden" name="lead_id" value={lead.id} />
          <input type="hidden" name="listing_id" value={listingId} />
          <select
            name="status"
            defaultValue={lead.status}
            className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm"
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Update status
          </button>
        </form>

        {lead.offered_price !== null && (
          <p className="mt-3 text-sm">
            Offer: <strong>{formatPrice(lead.offered_price)}</strong>
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <h2 className="text-sm font-semibold">Add activity</h2>
        <form action={addInteractionAction} className="mt-3 space-y-2">
          <input type="hidden" name="lead_id" value={lead.id} />
          <input type="hidden" name="listing_id" value={listingId} />
          <div className="flex gap-2">
            <select
              name="kind"
              defaultValue="note"
              className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm"
            >
              <option value="note">Note</option>
              <option value="call">Call</option>
              <option value="text">Text sent</option>
              <option value="email">Email sent</option>
              <option value="task">Task</option>
            </select>
            <input
              name="body"
              required
              placeholder="What happened?"
              className="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
            >
              Log
            </button>
          </div>
        </form>
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <h2 className="text-sm font-semibold">History</h2>
        {interactions.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No activity yet.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {interactions.map((i) => (
              <li key={i.id} className="flex gap-3 text-sm">
                <span aria-hidden>{INTERACTION_ICONS[i.kind] ?? "•"}</span>
                <div className="flex-1">
                  <p className="whitespace-pre-wrap">{i.body}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
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

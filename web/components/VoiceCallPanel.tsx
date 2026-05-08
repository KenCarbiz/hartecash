"use client";

import { useEffect, useState, useTransition } from "react";

import {
  startBridgeCallAction,
  startVoiceCallAction,
} from "@/app/listings/[id]/voice-actions";
import {
  formatRelativeDate,
  type SellerIntake,
  type VoiceCall,
} from "@/lib/api";

/** AI voice agent panel — the wedge VAN doesn't have.
 *
 *  Lets a dealer kick off an outbound voice call to the seller. Shows
 *  the most recent call's transcript + structured-intake chips so the
 *  next rep walks into a hot conversation already briefed. */
export function VoiceCallPanel({
  leadId,
  listingId,
  sellerPhone,
  calls,
  defaultRepPhone = null,
}: {
  leadId: number | null;
  listingId: number;
  sellerPhone: string | null;
  calls: VoiceCall[];
  defaultRepPhone?: string | null;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const callable = !!leadId && !!sellerPhone;

  const startCall = () => {
    if (!leadId) return;
    setError(null);
    setSuccess(null);
    startTransition(async () => {
      const res = await startVoiceCallAction(leadId, listingId);
      if (!res.ok) {
        setError(res.error ?? "call failed");
        return;
      }
      setSuccess(
        res.status === "simulated"
          ? "Call queued in simulation mode (configure Twilio to dial for real)."
          : "Call initiated. Refresh in ~30s for the transcript + intake.",
      );
    });
  };

  const latest = calls[0] ?? null;

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">AI voice agent</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Outbound call · structured intake on hangup
          </p>
        </div>
        <span className="badge bg-violet-100 text-violet-700">Beta</span>
      </div>

      <div className="space-y-3 p-4">
        {!leadId ? (
          <p className="text-xs text-ink-500">
            Claim this listing as a lead to enable AI voice outreach.
          </p>
        ) : !sellerPhone ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800">
            No seller phone on this listing — call disabled.
          </p>
        ) : (
          <p className="rounded-md border border-ink-200 bg-ink-50 px-2.5 py-1.5 text-[11px] text-ink-600">
            Recipient: <span className="font-mono text-ink-900">{formatPhone(sellerPhone)}</span>
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={startCall}
            disabled={!callable || pending}
            className="btn-primary text-xs"
          >
            {pending
              ? "Dialing…"
              : calls.length === 0
              ? "Place AI voice call"
              : "Place another call"}
          </button>
          {success && (
            <p className="self-center text-[11px] text-emerald-700">
              ✓ {success}
            </p>
          )}
          {error && (
            <p className="self-center text-[11px] text-rose-700">⚠ {error}</p>
          )}
        </div>

        {leadId && sellerPhone && (
          <BridgeCallForm
            leadId={leadId}
            listingId={listingId}
            defaultRepPhone={defaultRepPhone}
          />
        )}

        {latest && <LatestCallView call={latest} />}

        {calls.length > 1 && (
          <details className="rounded-md border border-ink-200 bg-white">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-700">
              Earlier calls ({calls.length - 1})
            </summary>
            <ol className="divide-y divide-ink-100">
              {calls.slice(1).map((c) => (
                <li key={c.id} className="px-3 py-2 text-xs">
                  <div className="flex items-baseline justify-between">
                    <span className="text-ink-700">
                      {formatRelativeDate(c.created_at)}
                    </span>
                    <span className="tabular text-ink-500">
                      {c.duration_seconds ? `${c.duration_seconds}s · ` : ""}
                      {c.status}
                    </span>
                  </div>
                  {c.intake?.next_step && (
                    <p className="mt-0.5 text-[11px] text-ink-600">
                      next: {c.intake.next_step}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </div>
  );
}

function LatestCallView({ call }: { call: VoiceCall }) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between text-[11px] text-ink-500">
        <span>
          {formatRelativeDate(call.created_at)} · {call.status}
          {call.duration_seconds ? ` · ${call.duration_seconds}s` : ""}
        </span>
        <span className="tabular">{call.turns?.length ?? 0} turns</span>
      </div>

      <IntakeChips intake={call.intake} />

      {call.turns && call.turns.length > 0 && (
        <details className="rounded-md border border-ink-200 bg-white">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-700">
            Transcript ({call.turns.length} turns)
          </summary>
          <ol className="max-h-60 overflow-y-auto px-3 pb-3 pt-1 space-y-1.5 text-xs">
            {call.turns.map((t, idx) => (
              <li
                key={idx}
                className={`rounded-md px-2 py-1.5 ${
                  t.role === "ai"
                    ? "bg-violet-50 text-violet-900"
                    : "bg-ink-50 text-ink-900"
                }`}
              >
                <span className="text-[10px] uppercase tracking-wider opacity-70">
                  {t.role === "ai" ? "AI" : "Seller"}
                </span>
                <p className="whitespace-pre-wrap">{t.text}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

const TITLE_LABELS: Record<string, string> = {
  in_hand: "Title in hand",
  lien_on_it: "Lien on title",
  lost: "Title lost",
  in_mail: "Title in mail",
  unknown: "Title unknown",
};

const MOTIVATION_PALETTE: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-800 border-emerald-200",
  medium: "bg-amber-50 text-amber-800 border-amber-200",
  low: "bg-ink-100 text-ink-700 border-ink-200",
  unknown: "bg-ink-100 text-ink-500 border-ink-200",
};

function IntakeChips({ intake }: { intake: SellerIntake | undefined | null }) {
  if (!intake || Object.keys(intake).length === 0) {
    return (
      <p className="text-[11px] text-ink-500">
        Structured intake fills in when the call ends and Claude reads the
        transcript.
      </p>
    );
  }
  const chips: { label: string; value: string; tone?: string }[] = [];

  if (intake.asking_price_floor != null) {
    chips.push({
      label: "Asking ↓",
      value: formatMoney(intake.asking_price_floor),
      tone: "bg-emerald-100 text-emerald-800 border-emerald-200",
    });
  }
  if (intake.mileage_confirmed != null) {
    chips.push({
      label: "Miles",
      value: `${intake.mileage_confirmed.toLocaleString()} mi`,
    });
  }
  if (intake.title_status && intake.title_status !== "unknown") {
    chips.push({
      label: "Title",
      value: TITLE_LABELS[intake.title_status] ?? intake.title_status,
    });
  }
  if (intake.lien_balance != null) {
    chips.push({ label: "Lien", value: formatMoney(intake.lien_balance) });
  }
  if (intake.drivable && intake.drivable !== "unknown") {
    chips.push({
      label: "Drivable",
      value: intake.drivable === "yes" ? "Yes" : "No",
      tone:
        intake.drivable === "yes"
          ? "bg-emerald-100 text-emerald-800 border-emerald-200"
          : "bg-rose-100 text-rose-800 border-rose-200",
    });
  }
  if (intake.motivation_level && intake.motivation_level !== "unknown") {
    chips.push({
      label: "Motivation",
      value: intake.motivation_level,
      tone: MOTIVATION_PALETTE[intake.motivation_level],
    });
  }
  if (intake.next_step) {
    chips.push({
      label: "Next",
      value: intake.next_step.replace(/_/g, " "),
      tone: "bg-violet-100 text-violet-800 border-violet-200",
    });
  }

  return (
    <div className="space-y-2">
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <span
              key={c.label + c.value}
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] ${
                c.tone ?? "bg-white text-ink-700 border-ink-200"
              }`}
            >
              <span className="text-[9px] uppercase tracking-wider opacity-70">
                {c.label}
              </span>
              <span className="font-medium">{c.value}</span>
            </span>
          ))}
        </div>
      )}

      {intake.accidents_disclosed && intake.accidents_disclosed.length > 0 && (
        <FlagRow label="Accidents" items={intake.accidents_disclosed} />
      )}
      {intake.mechanical_issues && intake.mechanical_issues.length > 0 && (
        <FlagRow label="Mechanical" items={intake.mechanical_issues} />
      )}
      {intake.body_damage_disclosed && intake.body_damage_disclosed.length > 0 && (
        <FlagRow label="Body damage" items={intake.body_damage_disclosed} />
      )}
      {intake.aftermarket_mods && intake.aftermarket_mods.length > 0 && (
        <FlagRow label="Mods" items={intake.aftermarket_mods} />
      )}

      {intake.willing_to_meet_when && (
        <p className="rounded-md border border-ink-200 bg-ink-50 px-2.5 py-1.5 text-xs text-ink-800">
          <span className="text-[10px] uppercase tracking-wider text-ink-500 mr-1.5">
            When
          </span>
          {intake.willing_to_meet_when}
        </p>
      )}
      {intake.location_for_inspection && (
        <p className="rounded-md border border-ink-200 bg-ink-50 px-2.5 py-1.5 text-xs text-ink-800">
          <span className="text-[10px] uppercase tracking-wider text-ink-500 mr-1.5">
            Where
          </span>
          {intake.location_for_inspection}
        </p>
      )}
      {intake.motivation_reason && (
        <p className="text-[11px] text-ink-600">
          <span className="text-ink-500">Why selling: </span>
          {intake.motivation_reason}
        </p>
      )}
    </div>
  );
}

function FlagRow({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className="text-ink-500 uppercase tracking-wider text-[10px]">
        {label}:
      </span>
      {items.map((it) => (
        <span
          key={it}
          className="rounded bg-rose-50 border border-rose-200 px-1.5 py-0.5 text-rose-800"
        >
          {it}
        </span>
      ))}
    </div>
  );
}

/** Click-to-call bridge: rep types their cell once, we ring them, then
 *  bridge to the seller. Caller ID is the dealership's Twilio number,
 *  not the rep's mobile, so the seller never learns their personal #. */
function BridgeCallForm({
  leadId,
  listingId,
  defaultRepPhone = null,
}: {
  leadId: number;
  listingId: number;
  defaultRepPhone?: string | null;
}) {
  const [pending, startTransition] = useTransition();
  const [repPhone, setRepPhone] = useState(defaultRepPhone ?? "");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Server-side User.phone is the source of truth; localStorage is a
  // fallback for legacy users who haven't saved one to their profile yet.
  useEffect(() => {
    if (defaultRepPhone) return;
    try {
      const saved = localStorage.getItem("aa.rep_phone");
      if (saved) setRepPhone(saved);
    } catch {
      /* ignore (Safari private mode etc.) */
    }
  }, [defaultRepPhone]);

  const onSubmit = (formData: FormData) => {
    setError(null);
    setSuccess(null);
    try {
      localStorage.setItem("aa.rep_phone", repPhone);
    } catch {
      /* ignore */
    }
    startTransition(async () => {
      const res = await startBridgeCallAction(leadId, listingId, formData);
      if (!res.ok) {
        setError(res.error ?? "bridge failed");
        return;
      }
      setSuccess(
        res.status === "simulated"
          ? "Bridge queued in simulation mode (configure Twilio to dial for real)."
          : "Your phone is ringing. Pick up to connect to the seller.",
      );
    });
  };

  return (
    <form
      action={onSubmit}
      className="rounded-md border border-ink-200 bg-white p-3 space-y-2"
    >
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-medium text-ink-700">Call from your phone</p>
        <p className="text-[10px] text-ink-500">
          Caller ID = your dealer line
        </p>
      </div>
      <div className="flex gap-2">
        <input
          type="tel"
          name="rep_phone"
          value={repPhone}
          onChange={(e) => setRepPhone(e.target.value)}
          placeholder="(813) 555-0100"
          autoComplete="tel"
          className="input flex-1 text-xs"
          required
        />
        <button
          type="submit"
          disabled={pending || !repPhone.trim()}
          className="btn-secondary text-xs"
        >
          {pending ? "Ringing…" : "Call now"}
        </button>
      </div>
      {success && (
        <p className="text-[11px] text-emerald-700">✓ {success}</p>
      )}
      {error && <p className="text-[11px] text-rose-700">⚠ {error}</p>}
    </form>
  );
}

function formatPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(-10);
  if (digits.length !== 10) return raw;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

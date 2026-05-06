import { notFound } from "next/navigation";

import { OfferActions } from "@/app/o/[token]/OfferActions";
import { getPublicOffer, type PublicOffer } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Public seller-facing offer page.
 *
 *  No login. No tracking. The dealer texts the seller a link with a
 *  64-char token; the seller taps it and sees a clean offer page with
 *  line-item deductions, a countdown, and one-tap accept / decline.
 *  This is the contrarian wedge — every other tool in this category
 *  is built dealer-side; nobody invests in the seller's experience.
 *
 *  Layout is intentionally minimal until the dashboard design pass —
 *  the right answer for "Apple-quality seller offer" is a dedicated
 *  visual treatment, and this page will get that. Today: clean and
 *  honest, no marketing chrome.
 */
export default async function PublicOfferPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const offer = await getPublicOffer(token);
  if (!offer) notFound();

  const expired =
    offer.status === "expired" ||
    (offer.status === "pending" && offer.expires_in_seconds <= 0);

  return (
    <main className="min-h-screen bg-ink-50 py-8 px-4">
      <div className="mx-auto max-w-md">
        {offer.dealer_name && (
          <p className="mb-3 text-center text-xs uppercase tracking-wider text-ink-500">
            Cash offer from {offer.dealer_name}
          </p>
        )}

        <h1 className="text-center text-xl font-semibold text-ink-900">
          For {offer.vehicle_label}
        </h1>

        <div className="mt-6 rounded-lg border border-ink-200 bg-white p-6 text-center shadow-sm">
          <p className="text-xs uppercase tracking-wider text-ink-500">
            Our cash offer
          </p>
          <p className="mt-1 text-5xl font-semibold tabular tracking-tight text-ink-900">
            {formatMoney(offer.amount_cents)}
          </p>
          {offer.status === "pending" && !expired ? (
            <p className="mt-3 text-xs text-ink-500">
              Locked for{" "}
              <span className="font-medium text-ink-800">
                {formatRemaining(offer.expires_in_seconds)}
              </span>
            </p>
          ) : (
            <StatusBadge status={offer.status} expired={expired} />
          )}
        </div>

        {offer.breakdown.length > 0 && (
          <section className="mt-5 rounded-lg border border-ink-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-ink-700">
              How we got here
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {offer.breakdown.map((line, idx) => (
                <li
                  key={idx}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="text-ink-700">{line.label}</span>
                  <span
                    className={`tabular ${
                      line.amount_cents < 0
                        ? "text-rose-700"
                        : "text-emerald-700"
                    }`}
                  >
                    {line.amount_cents > 0 ? "+" : ""}
                    {formatMoney(line.amount_cents)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {offer.notes && (
          <section className="mt-5 rounded-lg border border-ink-200 bg-white p-5 text-sm text-ink-700">
            <h2 className="text-xs uppercase tracking-wider text-ink-500">
              Note from the dealer
            </h2>
            <p className="mt-2 whitespace-pre-wrap">{offer.notes}</p>
          </section>
        )}

        {offer.photos.length > 0 && (
          <section className="mt-5">
            <div className="grid grid-cols-3 gap-1.5">
              {offer.photos.slice(0, 6).map((src, idx) => (
                <img
                  key={idx}
                  src={absolutize(src)}
                  alt=""
                  className="aspect-square w-full rounded-md object-cover bg-ink-100"
                />
              ))}
            </div>
          </section>
        )}

        <section className="mt-6 rounded-lg border border-ink-200 bg-white p-5">
          {offer.status === "pending" && !expired ? (
            <OfferActions token={token} />
          ) : (
            <ResolvedState offer={offer} expired={expired} />
          )}
        </section>

        <p className="mt-6 text-center text-[11px] text-ink-400">
          This offer is contingent on in-person inspection of the
          vehicle. Final price subject to verification of mileage,
          title, and condition.
        </p>
      </div>
    </main>
  );
}

function ResolvedState({
  offer,
  expired,
}: {
  offer: PublicOffer;
  expired: boolean;
}) {
  if (expired) {
    return (
      <p className="text-center text-sm text-ink-700">
        This offer has expired. Reply to your conversation with the dealer
        if you'd like a fresh one.
      </p>
    );
  }
  if (offer.status === "accepted") {
    return (
      <div className="text-center">
        <p className="text-base font-semibold text-emerald-700">
          ✓ Offer accepted
        </p>
        <p className="mt-1 text-sm text-ink-700">
          The dealer has been notified and will be in touch shortly to
          arrange the meeting.
        </p>
      </div>
    );
  }
  if (offer.status === "declined") {
    return (
      <p className="text-center text-sm text-ink-700">
        You declined this offer.
        {offer.dealer_name && (
          <> {offer.dealer_name} may follow up with a revised number.</>
        )}
      </p>
    );
  }
  if (offer.status === "withdrawn") {
    return (
      <p className="text-center text-sm text-ink-700">
        The dealer pulled this offer back. They may reach out with a new
        one — feel free to text or call them.
      </p>
    );
  }
  return null;
}

function StatusBadge({ status, expired }: { status: string; expired: boolean }) {
  let label = status;
  let tone = "bg-ink-100 text-ink-700";
  if (expired || status === "expired") {
    label = "Expired";
    tone = "bg-ink-200 text-ink-700";
  } else if (status === "accepted") {
    label = "Accepted";
    tone = "bg-emerald-100 text-emerald-800";
  } else if (status === "declined") {
    label = "Declined";
    tone = "bg-rose-100 text-rose-800";
  } else if (status === "withdrawn") {
    label = "Withdrawn";
    tone = "bg-amber-100 text-amber-800";
  }
  return (
    <span className={`mt-3 inline-block rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {label}
    </span>
  );
}

function absolutize(src: string): string {
  // Mirrored proxy URLs come back as relative paths; FB CDN URLs come
  // back absolute. Keep absolute as-is; front-relative paths with the
  // public API origin so the seller's browser can fetch them.
  if (src.startsWith("http://") || src.startsWith("https://")) return src;
  const base = process.env.FSBO_API_URL ?? "http://localhost:8000";
  return base.replace(/\/$/, "") + src;
}

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatRemaining(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const leftover = hours - days * 24;
    return leftover ? `${days}d ${leftover}h` : `${days}d`;
  }
  if (hours > 0) return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  return `${minutes}m`;
}

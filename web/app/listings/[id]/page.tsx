import Link from "next/link";
import { notFound } from "next/navigation";
import { LeadPanel } from "@/components/LeadPanel";
import {
  formatMileage,
  formatPrice,
  formatRelativeDate,
  getLeadForListing,
  getListing,
  listInteractions,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const CLASS_STYLES: Record<string, string> = {
  private_seller: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  dealer: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  scam: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  uncertain: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
  unclassified: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

function Field({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm">{value ?? "—"}</p>
    </div>
  );
}

export default async function ListingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const listingId = Number(id);
  if (!Number.isFinite(listingId)) notFound();

  const listing = await getListing(listingId);
  if (!listing) notFound();

  const lead = await getLeadForListing(listingId).catch(() => null);
  const interactions = lead ? await listInteractions(lead.id).catch(() => []) : [];

  const tag = CLASS_STYLES[listing.classification] ?? CLASS_STYLES.unclassified;
  const vehicleLine = [listing.year, listing.make, listing.model, listing.trim]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="space-y-6">
      <Link href="/listings" className="text-sm text-slate-500 hover:text-brand-600">
        ← Back to listings
      </Link>

      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{vehicleLine || listing.title || "Listing"}</h1>
          <p className="mt-1 text-sm text-slate-500">{listing.title}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${tag}`}>
          {listing.classification.replace("_", " ")}
          {listing.classification_confidence !== null &&
            ` · ${Math.round(listing.classification_confidence * 100)}%`}
        </span>
      </header>

      {listing.images.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {listing.images.slice(0, 8).map((src) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={src}
              src={src}
              alt=""
              className="aspect-video w-full rounded object-cover bg-slate-200 dark:bg-slate-800"
            />
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <Field label="Price" value={<span className="font-semibold">{formatPrice(listing.price)}</span>} />
        <Field label="Mileage" value={formatMileage(listing.mileage)} />
        <Field
          label="Location"
          value={[listing.city, listing.state, listing.zip_code].filter(Boolean).join(", ") || "—"}
        />
        <Field label="Source" value={listing.source} />
        <Field label="VIN" value={listing.vin ?? "—"} />
        <Field label="Year" value={listing.year ?? "—"} />
        <Field label="Make" value={listing.make ?? "—"} />
        <Field label="Model" value={listing.model ?? "—"} />
      </div>

      {listing.description && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-sm font-semibold">Description</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
            {listing.description}
          </p>
        </div>
      )}

      {listing.classification_reason && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-sm font-semibold">Classifier reasoning</h2>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
            {listing.classification_reason}
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <a
          href={listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          View original listing ↗
        </a>
        {listing.seller_phone && (
          <a
            href={`tel:${listing.seller_phone}`}
            className="rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Call {listing.seller_phone}
          </a>
        )}
        {listing.seller_phone && (
          <a
            href={`sms:${listing.seller_phone}`}
            className="rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Text seller
          </a>
        )}
      </div>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Lead workspace</h2>
        <LeadPanel listingId={listing.id} lead={lead} interactions={interactions} />
      </section>

      <div className="text-xs text-slate-500">
        First seen {formatRelativeDate(listing.first_seen_at)} · last updated{" "}
        {formatRelativeDate(listing.last_seen_at)}
      </div>
    </div>
  );
}

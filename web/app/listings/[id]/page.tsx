import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/AppShell";
import { ComposePanel } from "@/components/ComposePanel";
import { LeadPanel } from "@/components/LeadPanel";
import { ListingTimeline } from "@/components/ListingTimeline";
import { MarketBadge } from "@/components/MarketBadge";
import { QualityPanel } from "@/components/QualityPanel";
import { VehicleFilePanel } from "@/components/VehicleFilePanel";
import {
  formatMileage,
  formatPrice,
  formatRelativeDate,
  getLeadForListing,
  getListing,
  getListingStats,
  getMarketEstimate,
  getVehicleFile,
  listInteractions,
  listTemplates,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const CLASS_BADGE: Record<string, string> = {
  private_seller: "bg-emerald-100 text-emerald-800",
  dealer: "bg-amber-100 text-amber-800",
  scam: "bg-rose-100 text-rose-800",
  uncertain: "bg-ink-100 text-ink-700",
  unclassified: "bg-ink-100 text-ink-600",
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mt-1 text-sm tabular">{value ?? "—"}</p>
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
  const templates = await listTemplates().catch(() => []);
  const vehicleFile = await getVehicleFile(listingId).catch(() => null);
  const market = await getMarketEstimate(listingId).catch(() => null);
  const stats = await getListingStats(listingId).catch(() => null);

  const vehicleLine = [listing.year, listing.make, listing.model, listing.trim]
    .filter(Boolean)
    .join(" ");

  const badge = CLASS_BADGE[listing.classification] ?? CLASS_BADGE.unclassified;

  return (
    <>
      <Link href="/listings" className="btn-ghost -ml-2 mb-3 text-xs">
        ← Back to listings
      </Link>

      <PageHeader
        title={vehicleLine || listing.title || "Listing"}
        subtitle={listing.title && listing.title !== vehicleLine ? listing.title : undefined}
        actions={
          <>
            {listing.seller_phone && (
              <a href={`sms:${listing.seller_phone}`} className="btn-secondary">
                Text seller
              </a>
            )}
            {listing.seller_phone && (
              <a href={`tel:${listing.seller_phone}`} className="btn-secondary">
                Call
              </a>
            )}
            <a
              href={listing.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
            >
              View source ↗
            </a>
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-5">
          {listing.images.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {listing.images.slice(0, 6).map((src) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={src}
                  src={src}
                  alt=""
                  className="aspect-video w-full rounded-md object-cover border border-ink-200 bg-ink-100"
                />
              ))}
            </div>
          )}

          <div className="panel p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="kpi-value">{formatPrice(listing.price)}</p>
                <p className="mt-0.5 text-xs text-ink-500">
                  {formatMileage(listing.mileage)} ·{" "}
                  {[listing.city, listing.state, listing.zip_code].filter(Boolean).join(", ") ||
                    "—"}
                </p>
              </div>
              <span className={`badge ${badge}`}>
                {listing.classification.replace("_", " ")}
                {listing.classification_confidence !== null &&
                  ` · ${Math.round(listing.classification_confidence * 100)}%`}
              </span>
            </div>

            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-4 pt-5 border-t border-ink-200">
              <Field label="VIN" value={listing.vin ?? "—"} />
              <Field label="Year" value={listing.year ?? "—"} />
              <Field label="Make" value={listing.make ?? "—"} />
              <Field label="Model" value={listing.model ?? "—"} />
              <Field label="Trim" value={listing.trim ?? "—"} />
              <Field label="Source" value={listing.source} />
              <Field
                label="First seen"
                value={formatRelativeDate(listing.first_seen_at)}
              />
              <Field
                label="Last updated"
                value={formatRelativeDate(listing.last_seen_at)}
              />
            </div>
          </div>

          {listing.description && (
            <div className="panel">
              <div className="panel-header">
                <h2 className="text-sm font-semibold">Description</h2>
              </div>
              <p className="whitespace-pre-wrap px-5 py-4 text-sm text-ink-700">
                {listing.description}
              </p>
            </div>
          )}

          {listing.classification_reason && (
            <div className="panel">
              <div className="panel-header">
                <h2 className="text-sm font-semibold">Classifier reasoning</h2>
              </div>
              <p className="px-5 py-4 text-sm text-ink-700">{listing.classification_reason}</p>
            </div>
          )}

          <VehicleFilePanel
            file={vehicleFile}
            primaryListingId={listing.id}
          />
        </div>

        <div className="lg:col-span-1 space-y-3">
          <QualityPanel listing={listing} />
          <MarketBadge estimate={market} />
          <ListingTimeline stats={stats} />
          <h2 className="text-sm font-semibold text-ink-700 pt-1">Lead workspace</h2>
          <LeadPanel listingId={listing.id} lead={lead} interactions={interactions} />
          {lead && (
            <ComposePanel
              listingId={listing.id}
              leadId={lead.id}
              sellerPhone={listing.seller_phone}
              templates={templates}
            />
          )}
        </div>
      </div>
    </>
  );
}

import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/AppShell";
import { ComposePanel } from "@/components/ComposePanel";
import { LeadPanel } from "@/components/LeadPanel";
import { ListingTimeline } from "@/components/ListingTimeline";
import { MarketBadge } from "@/components/MarketBadge";
import { PlateChip, VehicleFactsEditor } from "@/components/VehicleFactsEditor";
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
  listTeammates,
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

/** Single row in the vertical vehicle fact stack: fixed-width label on the
 *  left, value on the right. Monospace values (VIN) get a smaller font
 *  so the full string fits without wrapping. */
function FactRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-4 py-2">
      <dt className="w-28 shrink-0 text-xs uppercase tracking-wide text-ink-500">
        {label}
      </dt>
      <dd
        className={`text-sm tabular text-ink-900 ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value ?? "—"}
      </dd>
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
  const teammates = await listTeammates().catch(() => []);
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

      {/* Identity chips sit at the top-left, directly under the title.
          Order: VIN → LICENSE PLATE → COLOR. Any chip whose field is
          empty quietly disappears. */}
      {(listing.vin || listing.license_plate || listing.color) && (
        <div className="-mt-3 mb-5 flex flex-wrap items-center gap-2">
          {listing.vin && (
            <span
              className="inline-flex items-center gap-1 rounded-md bg-ink-100 px-2 py-1 font-mono text-xs text-ink-800"
              title="VIN"
            >
              <span className="text-[9px] uppercase tracking-wider text-ink-500">
                VIN
              </span>
              {listing.vin}
            </span>
          )}
          <PlateChip
            plate={listing.license_plate}
            state={listing.license_plate_state}
          />
          {listing.color && (
            <span
              className="inline-flex items-center gap-1 rounded-md bg-ink-100 px-2 py-1 text-xs text-ink-800"
              title="Color"
            >
              <span className="text-[9px] uppercase tracking-wider text-ink-500">
                Color
              </span>
              {listing.color}
            </span>
          )}
        </div>
      )}

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

            {/* Vehicle box — vertical top-to-bottom stack in the exact order
                dealers read a buyer's guide: YEAR, MAKE/MODEL, VIN, PLATE,
                MILES, COLOR, DRIVABLE. Keeps scan-time short when flipping
                between listings. */}
            <dl className="mt-5 divide-y divide-ink-100 border-t border-ink-200 pt-2">
              <FactRow
                label="Year"
                value={listing.year ?? "—"}
              />
              <FactRow
                label="Make / Model"
                value={
                  [listing.make, listing.model, listing.trim]
                    .filter(Boolean)
                    .join(" ") || "—"
                }
              />
              <FactRow label="VIN" value={listing.vin ?? "—"} mono />
              <FactRow
                label="Plate"
                value={
                  listing.license_plate ? (
                    <span className="font-mono">
                      {listing.license_plate_state && (
                        <span className="mr-1 text-[10px] uppercase tracking-wider text-ink-500">
                          {listing.license_plate_state}
                        </span>
                      )}
                      {listing.license_plate}
                    </span>
                  ) : (
                    "—"
                  )
                }
              />
              <FactRow label="Miles" value={formatMileage(listing.mileage)} />
              <FactRow label="Color" value={listing.color ?? "—"} />
              <FactRow
                label="Drivable"
                value={
                  listing.drivable === true
                    ? "Yes"
                    : listing.drivable === false
                    ? "No"
                    : "—"
                }
              />
            </dl>

            <div className="mt-4 border-t border-ink-200 pt-4">
              <VehicleFactsEditor
                listingId={listing.id}
                initial={{
                  license_plate: listing.license_plate,
                  license_plate_state: listing.license_plate_state,
                  color: listing.color,
                  vin: listing.vin,
                  drivable: listing.drivable,
                }}
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-500">
              <span>Source: {listing.source}</span>
              <span>First seen {formatRelativeDate(listing.first_seen_at)}</span>
              <span>Updated {formatRelativeDate(listing.last_seen_at)}</span>
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
          <LeadPanel
            listingId={listing.id}
            lead={lead}
            interactions={interactions}
            teammates={teammates}
          />
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

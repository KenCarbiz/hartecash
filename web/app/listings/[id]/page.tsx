import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/AppShell";
import { ComposePanel } from "@/components/ComposePanel";
import { LeadPanel } from "@/components/LeadPanel";
import { ListingTimeline } from "@/components/ListingTimeline";
import { MarketBadge } from "@/components/MarketBadge";
import { ConditionPanel } from "@/components/ConditionPanel";
import { HistoryReportPanel } from "@/components/HistoryReportPanel";
import { OfferComposerPanel } from "@/components/OfferComposerPanel";
import { PlateChip, VehicleFactsEditor } from "@/components/VehicleFactsEditor";
import { QualityPanel } from "@/components/QualityPanel";
import { UnifiedFeedPanel } from "@/components/UnifiedFeedPanel";
import { VehicleFilePanel } from "@/components/VehicleFilePanel";
import { VoiceCallPanel } from "@/components/VoiceCallPanel";
import {
  formatMileage,
  formatPrice,
  formatRelativeDate,
  getCachedHistoryReport,
  getLeadFeed,
  getLeadForListing,
  isLeadUnread,
  markLeadSeen,
  getListing,
  getListingStats,
  getMarketEstimate,
  getNotificationPrefs,
  getVehicleFile,
  listInteractions,
  listOffersForLead,
  listTeammates,
  listTemplates,
  listVoiceCalls,
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

  // Listing is required for the page; everything else is parallel-safe.
  // Lead must come before interactions (interactions needs lead.id) so we
  // run lead+listing first, then fan out the rest in one Promise.all.
  const [listing, lead] = await Promise.all([
    getListing(listingId),
    getLeadForListing(listingId).catch(() => null),
  ]);
  if (!listing) notFound();

  // Visiting the listing detail page is implicit "I read the inbound
  // thread" — clear the unread badge if there is one.
  if (lead?.id && isLeadUnread(lead)) {
    await markLeadSeen(lead.id).catch(() => null);
  }

  const [
    interactions,
    templates,
    teammates,
    vehicleFile,
    market,
    stats,
    feed,
    voiceCalls,
    historyReport,
    offers,
    notifPrefs,
  ] = await Promise.all([
    lead ? listInteractions(lead.id).catch(() => []) : Promise.resolve([]),
    listTemplates().catch(() => []),
    listTeammates().catch(() => []),
    getVehicleFile(listingId).catch(() => null),
    getMarketEstimate(listingId).catch(() => null),
    getListingStats(listingId).catch(() => null),
    lead ? getLeadFeed(lead.id).catch(() => []) : Promise.resolve([]),
    lead ? listVoiceCalls(lead.id).catch(() => []) : Promise.resolve([]),
    getCachedHistoryReport(listingId).catch(() => null),
    lead ? listOffersForLead(lead.id).catch(() => []) : Promise.resolve([]),
    getNotificationPrefs().catch(() => null),
  ]);

  // App origin so the OfferComposer can show the dealer the public
  // offer URL they'll text the seller.
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? "http";
  const appOrigin = `${proto}://${host}`;

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

          {/* Unified per-lead activity feed: voice calls, SMS, notes,
              status changes — chronological. The "messaging hub" VAN
              ships in their Lincoln Park release, with our voice-call
              + intake-summary entries folded in. */}
          {lead && <UnifiedFeedPanel entries={feed} />}
        </div>

        <div className="lg:col-span-1 space-y-3">
          <QualityPanel listing={listing} />
          <ConditionPanel condition={listing.condition} />
          <HistoryReportPanel
            listingId={listing.id}
            hasVin={!!listing.vin && listing.vin.length === 17}
            report={historyReport}
          />
          <MarketBadge estimate={market} />
          <ListingTimeline stats={stats} />
          <h2 className="text-sm font-semibold text-ink-700 pt-1">Lead workspace</h2>
          <LeadPanel
            listingId={listing.id}
            lead={lead}
            interactions={interactions}
            teammates={teammates}
          />
          <VoiceCallPanel
            leadId={lead?.id ?? null}
            listingId={listing.id}
            sellerPhone={listing.seller_phone}
            calls={voiceCalls}
            defaultRepPhone={notifPrefs?.phone ?? null}
          />
          <OfferComposerPanel
            leadId={lead?.id ?? null}
            listingId={listing.id}
            appOrigin={appOrigin}
            offers={offers}
            marketMedian={market?.median ?? null}
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

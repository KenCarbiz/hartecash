import Link from "next/link";
import {
  type Listing,
  formatMileage,
  formatPrice,
  formatRelativeDate,
} from "@/lib/api";

const CLASS_STYLES: Record<string, string> = {
  private_seller: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  dealer: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  scam: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  uncertain: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
  unclassified: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

export function ListingCard({ listing }: { listing: Listing }) {
  const tag = CLASS_STYLES[listing.classification] ?? CLASS_STYLES.unclassified;
  const heroImage = listing.images[0];
  const vehicleLine = [listing.year, listing.make, listing.model]
    .filter(Boolean)
    .join(" ");

  return (
    <Link
      href={`/listings/${listing.id}`}
      className="flex gap-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 hover:border-brand-500 transition"
    >
      <div className="h-24 w-32 flex-shrink-0 overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
        {heroImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={heroImage}
            alt={listing.title ?? ""}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">
            no image
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-medium">
              {vehicleLine || listing.title || "Untitled listing"}
            </p>
            <p className="truncate text-sm text-slate-500">{listing.title}</p>
          </div>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tag}`}>
            {listing.classification.replace("_", " ")}
          </span>
        </div>

        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="font-semibold">{formatPrice(listing.price)}</span>
          <span className="text-slate-500">{formatMileage(listing.mileage)}</span>
          <span className="text-slate-500">
            {[listing.city, listing.state].filter(Boolean).join(", ") || listing.zip_code || "—"}
          </span>
          <span className="text-slate-500">
            {listing.source} · {formatRelativeDate(listing.posted_at ?? listing.first_seen_at)}
          </span>
        </div>
      </div>
    </Link>
  );
}

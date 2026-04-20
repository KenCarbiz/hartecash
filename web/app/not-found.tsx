import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-20 text-center">
      <h1 className="text-3xl font-semibold">Not found</h1>
      <p className="mt-2 text-sm text-slate-500">That listing doesn&apos;t exist or has been removed.</p>
      <Link
        href="/listings"
        className="mt-6 inline-block rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
      >
        Back to listings
      </Link>
    </div>
  );
}

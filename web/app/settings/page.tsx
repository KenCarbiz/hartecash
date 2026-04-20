import { PageHeader } from "@/components/AppShell";
import { ApiKeysPanel } from "@/components/ApiKeysPanel";
import { FsboApiError, listApiKeys } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  let keys: Awaited<ReturnType<typeof listApiKeys>> = [];
  let error: string | null = null;
  try {
    keys = await listApiKeys();
  } catch (err) {
    error = err instanceof FsboApiError ? err.message : "API unreachable";
  }

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Dealer configuration and integration keys."
      />

      {error && (
        <div className="panel mb-4 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Can&apos;t reach the FSBO API. ({error})
        </div>
      )}

      <div className="space-y-6 max-w-4xl">
        <div className="panel p-5">
          <h2 className="text-sm font-semibold">Dealer profile</h2>
          <p className="text-xs text-ink-500 mt-0.5">
            Dealer identity is currently stubbed. Auth wiring is next.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <Field label="Dealer ID" value="demo-dealer" />
            <Field label="Mode" value="Development" />
            <Field label="Default user" value="me" />
            <Field label="Daily message goal" value="60" />
          </dl>
        </div>

        <ApiKeysPanel keys={keys} />

        <div className="panel p-5">
          <h2 className="text-sm font-semibold">Twilio messaging</h2>
          <p className="text-xs text-ink-500 mt-0.5">
            A2P 10DLC registration status. Configure via environment variables
            on the API service.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <Field label="Status" value="Configure via env vars" />
            <Field label="Brand tier" value="—" />
          </dl>
          <p className="mt-4 text-[11px] text-ink-500">
            Set{" "}
            <code className="rounded bg-ink-100 px-1">TWILIO_ACCOUNT_SID</code>
            ,{" "}
            <code className="rounded bg-ink-100 px-1">TWILIO_AUTH_TOKEN</code>
            , and{" "}
            <code className="rounded bg-ink-100 px-1">
              TWILIO_MESSAGING_SERVICE_SID
            </code>{" "}
            on the API service to enable outbound SMS.
          </p>
        </div>
      </div>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-1 text-sm font-medium tabular">{value}</dd>
    </div>
  );
}

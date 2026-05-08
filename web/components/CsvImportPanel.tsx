"use client";

import { useRef, useState, useTransition } from "react";

import { importLeadsAction } from "@/app/settings/import-action";
import type { ImportResult } from "@/lib/api";

export function CsvImportPanel() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const submit = (fd: FormData) => {
    setError(null);
    setResult(null);
    startTransition(async () => {
      const res = await importLeadsAction(fd);
      if (res.ok && res.result) {
        setResult(res.result);
        if (fileRef.current) fileRef.current.value = "";
        setFileName(null);
      } else {
        setError(res.error ?? "Import failed");
      }
    });
  };

  return (
    <div className="panel p-5">
      <h2 className="text-sm font-semibold">Import leads from CSV</h2>
      <p className="text-[11px] text-ink-500 mt-0.5">
        Migrate from VAN, Frazer, DealerSocket, or any spreadsheet. We
        match column headers loosely (case-insensitive, spaces or
        underscores). Re-importing the same file is safe — duplicates
        are skipped.
      </p>

      <form action={submit} className="mt-4 space-y-3">
        <label className="block">
          <span className="label">CSV file</span>
          <input
            ref={fileRef}
            type="file"
            name="file"
            accept=".csv,text/csv"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-brand-700"
            required
          />
          {fileName && (
            <p className="mt-1 text-[11px] text-ink-500">Selected: {fileName}</p>
          )}
        </label>

        <details className="rounded-md border border-ink-200 bg-ink-50 px-3 py-2 text-xs text-ink-700">
          <summary className="cursor-pointer font-medium">
            Recognized columns
          </summary>
          <ul className="mt-2 space-y-0.5 text-[11px] text-ink-600">
            <li>
              <strong>Identifier (need at least one):</strong> phone, email,
              vin
            </li>
            <li>
              <strong>Vehicle:</strong> year, make, model, vehicle, title
            </li>
            <li>
              <strong>Numbers:</strong> price, mileage, miles ($ and commas OK)
            </li>
            <li>
              <strong>Location:</strong> city, state, zip
            </li>
            <li>
              <strong>CRM fields:</strong> assigned_to / owner / rep, status,
              notes
            </li>
            <li>
              Unknown columns are silently skipped — keep the rest of your
              spreadsheet intact.
            </li>
          </ul>
        </details>

        <button
          type="submit"
          disabled={pending || !fileName}
          className="btn-primary text-sm"
        >
          {pending ? "Importing…" : "Import"}
        </button>
      </form>

      {result && (
        <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          ✓ Imported <strong>{result.imported}</strong> lead
          {result.imported === 1 ? "" : "s"}.
          {result.skipped_duplicates > 0 && (
            <> Skipped {result.skipped_duplicates} duplicate
              {result.skipped_duplicates === 1 ? "" : "s"}.</>
          )}
          {result.errors.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-amber-800">
                {result.errors.length} row error
                {result.errors.length === 1 ? "" : "s"}
              </summary>
              <ul className="mt-1.5 space-y-0.5 text-xs text-amber-900">
                {result.errors.slice(0, 25).map((err) => (
                  <li key={err.row}>
                    <span className="tabular">Row {err.row}:</span>{" "}
                    {err.error}
                  </li>
                ))}
                {result.errors.length > 25 && (
                  <li className="text-amber-700">
                    …and {result.errors.length - 25} more.
                  </li>
                )}
              </ul>
            </details>
          )}
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          ⚠ {error}
        </div>
      )}
    </div>
  );
}

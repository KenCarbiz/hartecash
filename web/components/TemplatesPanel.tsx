"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  createTemplateAction,
  deleteTemplateAction,
  updateTemplateAction,
} from "@/app/settings/template-actions";
import type { MessageTemplate } from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  outreach: "Opener",
  vin_request: "VIN request",
  offer: "Offer",
  follow_up: "Follow-up",
  custom: "Custom",
};

const CATEGORY_STYLES: Record<string, string> = {
  outreach: "bg-sky-100 text-sky-800",
  vin_request: "bg-violet-100 text-violet-800",
  offer: "bg-emerald-100 text-emerald-800",
  follow_up: "bg-amber-100 text-amber-800",
  custom: "bg-ink-100 text-ink-700",
};

export function TemplatesPanel({ templates }: { templates: MessageTemplate[] }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const runAction = (
    action: (fd: FormData) => Promise<{ ok: boolean; error?: string }>,
    fd: FormData,
    onOk?: () => void,
  ) => {
    setError(null);
    startTransition(async () => {
      const res = await action(fd);
      if (!res.ok && res.error) setError(res.error);
      else {
        onOk?.();
        router.refresh();
      }
    });
  };

  const runDelete = (id: number) => {
    if (!confirm("Delete this template?")) return;
    startTransition(async () => {
      const fd = new FormData();
      fd.set("id", String(id));
      await deleteTemplateAction(fd);
      router.refresh();
    });
  };

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold">Message templates</h2>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Edit or add templates. Use {"{{year}} {{make}} {{model}}"} placeholders
            (plus {"{{city}} {{price}} {{offer}}"}) — they fill in per-listing.
          </p>
        </div>
        {!adding && (
          <button
            type="button"
            onClick={() => {
              setAdding(true);
              setEditing(null);
              setError(null);
            }}
            className="btn-primary"
          >
            New template
          </button>
        )}
      </div>

      {error && (
        <div className="border-b border-ink-200 bg-rose-50 p-3 text-sm text-rose-800">
          ⚠ {error}
        </div>
      )}

      {adding && (
        <TemplateEditor
          onSave={(fd) =>
            runAction(createTemplateAction, fd, () => setAdding(false))
          }
          onCancel={() => setAdding(false)}
          pending={pending}
          submitLabel="Create template"
        />
      )}

      {templates.length === 0 ? (
        <p className="p-5 text-sm text-ink-500">
          No templates yet. The backend auto-seeds a starter set on first use.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="text-left font-medium px-4 py-2.5">Name</th>
              <th className="text-left font-medium px-4 py-2.5">Category</th>
              <th className="text-left font-medium px-4 py-2.5">Preview</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {templates.map((t) => (
              <>
                <tr key={t.id} className="hover:bg-ink-50">
                  <td className="px-4 py-2.5 font-medium">{t.name}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`badge ${
                        CATEGORY_STYLES[t.category] ?? CATEGORY_STYLES.custom
                      }`}
                    >
                      {CATEGORY_LABELS[t.category] ?? t.category}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-ink-600 text-xs truncate max-w-md">
                    {t.body.length > 100 ? `${t.body.slice(0, 100)}…` : t.body}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() =>
                        setEditing((cur) => (cur === t.id ? null : t.id))
                      }
                      className="btn-ghost text-xs"
                    >
                      {editing === t.id ? "Close" : "Edit"}
                    </button>
                    <button
                      type="button"
                      onClick={() => runDelete(t.id)}
                      className="btn-ghost text-xs text-rose-600 hover:text-rose-700 ml-1"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
                {editing === t.id && (
                  <tr key={`${t.id}-edit`}>
                    <td colSpan={4} className="bg-ink-50">
                      <TemplateEditor
                        template={t}
                        onSave={(fd) =>
                          runAction(updateTemplateAction, fd, () =>
                            setEditing(null),
                          )
                        }
                        onCancel={() => setEditing(null)}
                        pending={pending}
                        submitLabel="Save changes"
                      />
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TemplateEditor({
  template,
  onSave,
  onCancel,
  pending,
  submitLabel,
}: {
  template?: MessageTemplate;
  onSave: (fd: FormData) => void;
  onCancel: () => void;
  pending: boolean;
  submitLabel: string;
}) {
  return (
    <form
      action={onSave}
      className="space-y-3 border-y border-ink-200 bg-ink-50 p-4"
    >
      {template && <input type="hidden" name="id" value={template.id} />}
      <div className="grid grid-cols-3 gap-3">
        <label className="col-span-2 block">
          <span className="label">Name</span>
          <input
            name="name"
            required
            defaultValue={template?.name ?? ""}
            placeholder="e.g. Opener — direct cash"
            className="input mt-1"
          />
        </label>
        <label className="block">
          <span className="label">Category</span>
          <select
            name="category"
            defaultValue={template?.category ?? "outreach"}
            className="input mt-1"
          >
            {Object.entries(CATEGORY_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block">
        <span className="label">Body</span>
        <textarea
          name="body"
          required
          rows={4}
          defaultValue={template?.body ?? ""}
          placeholder="Hi — saw your {{year}} {{make}} {{model}} in {{city}}…"
          className="input mt-1 font-mono text-xs"
        />
      </label>
      <div className="flex items-center gap-2">
        <button type="submit" disabled={pending} className="btn-primary text-xs">
          {pending ? "Saving…" : submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary text-xs"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

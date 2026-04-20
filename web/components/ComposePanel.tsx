"use client";

import { useState, useTransition } from "react";

import type { MessageTemplate } from "@/lib/api";
import {
  composeOpenerAction,
  renderTemplateAction,
  logSentMessageAction,
} from "@/app/listings/[id]/compose-actions";

type Tone = "direct" | "friendly" | "cash-buyer";

interface ComposePanelProps {
  listingId: number;
  leadId: number | null;
  sellerPhone: string | null;
  templates: MessageTemplate[];
}

const TONES: { value: Tone; label: string }[] = [
  { value: "direct", label: "Direct" },
  { value: "friendly", label: "Friendly" },
  { value: "cash-buyer", label: "Cash buyer" },
];

export function ComposePanel({
  listingId,
  leadId,
  sellerPhone,
  templates,
}: ComposePanelProps) {
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState<Tone>("direct");
  const [source, setSource] = useState<string>("ai");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const generateAi = () => {
    setError(null);
    startTransition(async () => {
      const res = await composeOpenerAction(listingId, tone);
      if ("message" in res) {
        setMessage(res.message);
        setSource("ai");
      } else {
        setError(res.error);
      }
    });
  };

  const applyTemplate = (templateId: number) => {
    setError(null);
    startTransition(async () => {
      const res = await renderTemplateAction(templateId, listingId);
      if ("rendered" in res) {
        setMessage(res.rendered);
        setSource(`template-${templateId}`);
      } else {
        setError(res.error);
      }
    });
  };

  const logAndOpen = (method: "sms" | "copy") => {
    if (!message.trim()) return;
    startTransition(async () => {
      if (leadId) {
        await logSentMessageAction(leadId, listingId, message, source);
      }
      if (method === "sms" && sellerPhone) {
        const url = `sms:${sellerPhone}?body=${encodeURIComponent(message)}`;
        window.location.href = url;
      } else {
        await navigator.clipboard.writeText(message);
      }
    });
  };

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Compose outreach</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            AI-generated or template-based message to the seller.
          </p>
        </div>
        <span className="badge bg-brand-100 text-brand-700">Beta</span>
      </div>

      <div className="p-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {TONES.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setTone(t.value)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                tone === t.value
                  ? "bg-ink-900 text-white"
                  : "border border-ink-200 text-ink-700 hover:bg-ink-50"
              }`}
            >
              {t.label}
            </button>
          ))}
          <button
            type="button"
            onClick={generateAi}
            disabled={pending}
            className="btn-primary ml-auto text-xs"
          >
            {pending && source === "ai" ? "Generating…" : "✨ Generate with AI"}
          </button>
        </div>

        {templates.length > 0 && (
          <div>
            <p className="label mb-1.5">Or start from a template</p>
            <div className="flex flex-wrap gap-1.5">
              {templates.slice(0, 6).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => applyTemplate(t.id)}
                  disabled={pending}
                  className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-700 hover:bg-ink-50"
                  title={t.body}
                >
                  {t.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Your message will appear here. Edit before sending."
          rows={5}
          className="input font-sans leading-relaxed"
        />

        {error && (
          <p className="text-xs text-rose-600">⚠ {error}</p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-ink-500 tabular">
            {message.length} chars · {message.length > 320 ? "may split into 2 SMS" : "fits in 1 SMS"}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => logAndOpen("copy")}
              disabled={!message.trim() || pending}
              className="btn-secondary text-xs"
            >
              Copy
            </button>
            <button
              type="button"
              onClick={() => logAndOpen("sms")}
              disabled={!message.trim() || !sellerPhone || pending}
              className="btn-primary text-xs"
            >
              Open SMS →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Messenger content script.
 *
 * Runs on `messenger.com/marketplace/*` and on Marketplace's in-page
 * Messenger overlay (`facebook.com/marketplace/messages/*`). Watches
 * the chat DOM for new messages and extracts US phone numbers as
 * sellers reveal them.
 *
 * Why not parse Messenger GraphQL like we do for Marketplace? FB
 * Messenger uses a different API surface and a more aggressive
 * detection layer for automated readers. The DOM approach is
 * read-only, runs only when the dealer is already viewing a thread,
 * and never inspects encrypted-content metadata.
 *
 * Privacy posture: we extract ONLY 10/11-digit US phone numbers. We
 * never forward message bodies wholesale; the backend gets the phone
 * + a short ~80-char context snippet (so the dealer can tell "they
 * texted me 813-555-1234" from "office hours 9am-5pm 813-555-1234").
 */

import { callWorker } from "../lib/api";

// 10-digit US format with optional country code, parens/dashes/dots.
// Anchored on word boundaries to skip 10-digit IDs/order numbers.
const PHONE_RE =
  /(?<![\w])(?:\+?1[ \-. ]?)?\(?([2-9]\d{2})\)?[ \-. ]?(\d{3})[ \-. ]?(\d{4})(?![\w])/g;

// Phrases nearby that confirm this is actually a phone (not a tracking
// number that happens to fit the regex). When at least one shows up
// within ~40 chars of the digits, we forward; otherwise skip.
const PHONE_INDICATORS = [
  "call",
  "text",
  "phone",
  "number",
  "cell",
  "mobile",
  "ring",
  "reach",
  "contact",
  "dial",
  "hit me",
];

// Per-tab dedup so a re-render doesn't re-send the same phone.
const sentThisSession = new Set<string>();

interface MarketplaceContext {
  external_id: string | null;
  source: "facebook_marketplace";
}

function readMarketplaceContext(): MarketplaceContext {
  // Messenger pages with a marketplace listing reference stash the
  // listing id in a /t/<thread>?marketplace_listing_id=<id> query, or
  // in an inline link/anchor on the thread header. Walk both.
  const url = new URL(location.href);
  const fromQuery = url.searchParams.get("marketplace_listing_id");
  if (fromQuery && /^\d{8,20}$/.test(fromQuery)) {
    return { external_id: fromQuery, source: "facebook_marketplace" };
  }
  // DOM scan: any anchor link to /marketplace/item/<id>
  const anchor = document.querySelector<HTMLAnchorElement>(
    'a[href*="/marketplace/item/"]',
  );
  if (anchor) {
    const m = anchor.href.match(/\/marketplace\/item\/(\d+)/);
    if (m) return { external_id: m[1], source: "facebook_marketplace" };
  }
  return { external_id: null, source: "facebook_marketplace" };
}

function nearbyHasIndicator(text: string, idx: number): boolean {
  const lo = Math.max(0, idx - 40);
  const hi = Math.min(text.length, idx + 40);
  const window = text.slice(lo, hi).toLowerCase();
  return PHONE_INDICATORS.some((p) => window.includes(p));
}

function extractPhones(text: string): { digits: string; context: string }[] {
  const out: { digits: string; context: string }[] = [];
  for (const match of text.matchAll(PHONE_RE)) {
    const idx = match.index ?? 0;
    if (!nearbyHasIndicator(text, idx)) continue;
    const digits = (match[1] + match[2] + match[3]).replace(/\D/g, "");
    if (digits.length !== 10) continue;
    const start = Math.max(0, idx - 30);
    const end = Math.min(text.length, idx + match[0].length + 30);
    out.push({ digits, context: text.slice(start, end).trim() });
  }
  return out;
}

function forwardPhone(
  digits: string,
  context: string,
  ctx: MarketplaceContext,
): void {
  // Per-thread + per-phone dedup: don't spam the API as the user
  // re-renders the conversation.
  const key = `${location.pathname}|${digits}`;
  if (sentThisSession.has(key)) return;
  sentThisSession.add(key);

  void callWorker({
    kind: "sellerPhone",
    phone: digits,
    context,
    external_id: ctx.external_id,
    source: ctx.source,
  });
}

function scanMessages(): void {
  // Messenger renders message bubbles inside [data-testid="message_text"]
  // or [role="row"] containers. Be permissive: any element whose text
  // hasn't already been scanned this session.
  const ctx = readMarketplaceContext();
  if (!ctx.external_id) return; // only act when we know the listing

  const containers = document.querySelectorAll<HTMLElement>(
    "[data-testid='message_text'], [role='row'], [data-testid='message_bubble']",
  );
  containers.forEach((el) => {
    const text = (el.textContent ?? "").trim();
    if (text.length < 10 || text.length > 2000) return;
    for (const { digits, context } of extractPhones(text)) {
      forwardPhone(digits, context, ctx);
    }
  });
}

let scanScheduled = false;
function scheduleScan(): void {
  if (scanScheduled) return;
  scanScheduled = true;
  // Debounce to a single scan per animation frame so a chunky DOM
  // mutation doesn't trigger 50 walks.
  window.setTimeout(() => {
    scanScheduled = false;
    try {
      scanMessages();
    } catch (e) {
      void callWorker({
        kind: "telemetry",
        event: "content_script_error",
        url: location.href,
        extra: { where: "messenger", error: String(e) },
      });
    }
  }, 300);
}

const obs = new MutationObserver(() => scheduleScan());
obs.observe(document.body, { childList: true, subtree: true });
scheduleScan();

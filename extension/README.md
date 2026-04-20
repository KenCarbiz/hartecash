# AutoCurb browser extension

Augments Facebook Marketplace, Craigslist, and other FSBO marketplaces with
AutoCurb buyer tools while the dealer browses them natively.

## What it does

1. **Facebook Marketplace**: runs as a content script on `facebook.com/marketplace/*`,
   extracts listing metadata from the DOM as the dealer scrolls, and POSTs it
   back to `/sources/extension/ingest` so it gets classified, deduped, and
   joined into the dealer's feed.
2. **Overlay UI**: injects a floating AutoCurb widget on each listing page with:
   - "Claim as lead" one-click action
   - Prior-engagement badge ("Alice already reached out 3d ago")
   - VIN from photo (clicks the photo to OCR)
   - "Open in AutoCurb" deep-link
3. **Privacy**: the extension runs in the dealer's own browser session. The
   dealer is already logged into Facebook with their personal/business
   account. AutoCurb never stores Facebook credentials, only the public listing
   data the dealer is entitled to view.

## Architecture

```
extension/
├── manifest.json               # MV3 manifest
├── src/
│   ├── background/index.ts     # service worker — API calls, auth bridge
│   ├── content/
│   │   ├── facebook.ts         # FB Marketplace DOM extractor + overlay
│   │   └── craigslist.ts       # Craigslist overlay (data already scraped)
│   └── popup/index.tsx         # toolbar popup (quick status + settings)
└── icons/                      # 16/48/128 px
```

## Dev

```bash
cd extension
npm install
npm run build                    # builds to dist/
# Load unpacked from dist/ in chrome://extensions
```

## Legal posture

- Logged-in scraping of Marketplace is contentious. We mitigate by:
  - Running only in the user's own browser, on pages they're already viewing
  - No scrape-all behavior — only listings the user *opens*
  - Extension ToS requires dealer to have valid FB TOS-compliant usage
- We still recommend dealer legal review before enabling Marketplace features
  in production.

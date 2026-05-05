# Chrome Web Store listing — AutoAcquisition

Draft copy for the Web Store listing. Paste into the publisher
dashboard at chrome.google.com/webstore/devconsole.

## Short description (132 chars max)

Capture for-sale-by-owner vehicle listings from Facebook Marketplace
straight into your dealership's acquisition pipeline.

## Detailed description

AutoAcquisition is the dealer-acquisition companion to autoacquisition.io.
As you browse Facebook Marketplace, the extension quietly indexes the
private-seller vehicle listings you scroll past — title, price, mileage,
photos, seller profile — into your dealership's acquisition feed.

What you get out of the box:

  • Every FB Marketplace vehicle you scroll past becomes a lead
    candidate, scored by classifier (private seller vs. dealer vs. scam)
    and a 20-signal lead-quality engine.
  • One-click "Claim as lead" overlay on the listing detail page;
    instantly pulls the listing into your CRM with a contact-the-seller
    template.
  • AI vision pass (Claude Haiku 4.5) extracts the license plate, VIN
    (when visible in a photo), and a structured condition assessment —
    body damage, paint, interior, tires, plus damage flags — so you
    know what you're driving to look at.
  • Seller curbstoner detection: phone-number cluster graph + posting
    cadence histogram + identical-photo perceptual hashing.
  • Photo proxy: the extension and dashboard rehost FB CDN photos
    before Facebook expires them, so listings stay viewable forever.

Built for: licensed used-car dealers; private-seller acquisition
specialists; trade-in desks; wholesale buyers.

Not for: scraping at scale, reselling listing data, or any use outside
of legitimate vehicle acquisition by an authorized dealership.

## Permissions justification

  - storage: persist your API key + extension settings
    (chrome.storage.local).
  - activeTab + scripting: inject the GraphQL hook into the current
    Marketplace page to read public listing data (the dealer chose to
    view).
  - host: facebook.com/* — the extension only runs on Marketplace URLs.
  - host: *.craigslist.org/* and offerup.com/* — sibling FSBO sources
    coming online.

## Single-purpose

The single purpose of AutoAcquisition is to capture publicly-visible
private-seller vehicle listings into the dealer's
private acquisition pipeline. No other functionality.

## Data handling certification

  - Does not collect personally-identifiable information beyond what's
    publicly displayed on the listing page.
  - Does not sell listing inventory to third parties.
  - Uses the data only for the dealership that authenticated the
    extension.

Privacy policy: PRIVACY.md (also published at
autoacquisition.io/privacy).

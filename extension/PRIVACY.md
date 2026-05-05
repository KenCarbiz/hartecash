# AutoAcquisition — Privacy Policy

**Last updated:** 2026-05-05

AutoAcquisition is a Chrome extension that helps licensed automotive
dealers capture publicly-listed for-sale-by-owner (FSBO) vehicles from
Facebook Marketplace and other classifieds sites.

## What we collect

The extension captures and forwards to your dealership's AutoAcquisition
account **only** the public listing content the user is currently
browsing:

- The listing's title, description, price, mileage, year/make/model
- The listing's public photos (URLs, and copies we mirror to keep the
  detail page from breaking when the source site expires the URL)
- The listing's public location (city / state / ZIP)
- The seller's public profile name, profile URL, and join date —
  **only** when displayed publicly on the listing page
- The listing's external ID and URL

The extension forwards these to the AutoAcquisition API endpoint your
dealership configured (typically `api.autoacquisition.io`).

## What we do not collect

- Your Facebook credentials, cookies, or messaging contents
- The seller's email, phone (until you, the dealer, message the seller
  through Facebook to request it), or address
- Any content from non-Marketplace pages
- Browsing history outside of the marketplace pages you choose to view

## How the data is used

Listings are aggregated into your dealership's private acquisition
inventory inside AutoAcquisition. AI passes (vehicle condition
assessment, license plate / VIN OCR from photos) run server-side
against the photos in the listing to help you appraise the car.

## Authentication

The extension stores a single API key (`ac_live_…`) in
`chrome.storage.local` after you complete the install-code onboarding
flow. The key is dealer-scoped and revocable from your dealership's
settings page.

## Sharing

We do not sell or share your dealership's listing inventory with third
parties. Anthropic processes listing photos in the AI pipeline under
their data-processing agreement and does not retain them for training.

## Contact

Questions: privacy@autoacquisition.io

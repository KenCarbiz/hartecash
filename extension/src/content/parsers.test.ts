/**
 * Parser unit tests — pure functions only, no DOM.
 *
 * Run with `npx vitest` (see devDependencies).
 */

import { describe, expect, it } from "vitest";

import {
  extractCityState,
  extractMileage,
  extractPrice,
  extractYear,
  graphRecordToIngest,
  upgradeImageUrl,
  walkForListingRecords,
} from "./parsers";

describe("extractYear", () => {
  it("finds a 2000s year", () => {
    expect(extractYear("2018 Ford F-150 SuperCrew")).toBe(2018);
  });
  it("finds a late-90s year", () => {
    expect(extractYear("1998 Honda Civic Hatchback")).toBe(1998);
  });
  it("returns undefined on no year", () => {
    expect(extractYear("Clean daily driver")).toBeUndefined();
  });
  it("handles null/undefined", () => {
    expect(extractYear(null)).toBeUndefined();
    expect(extractYear(undefined)).toBeUndefined();
  });
});

describe("extractPrice", () => {
  it("parses $12,500", () => {
    expect(extractPrice("Asking $12,500 OBO")).toBe(12500);
  });
  it("parses $ 8500 with space", () => {
    expect(extractPrice("Price: $ 8500")).toBe(8500);
  });
  it("returns undefined for no price", () => {
    expect(extractPrice("great condition")).toBeUndefined();
  });
});

describe("extractMileage", () => {
  it("parses 85,000 miles", () => {
    expect(extractMileage("85,000 miles, one owner")).toBe(85000);
  });
  it("parses 85k miles", () => {
    expect(extractMileage("85k miles")).toBe(85000);
  });
  it("parses 85K MILES all caps", () => {
    expect(extractMileage("ONLY 85K MILES")).toBe(85000);
  });
  it("parses 120000 mi", () => {
    expect(extractMileage("120000 mi")).toBe(120000);
  });
  it("rejects absurd values", () => {
    // 600k is past our sanity ceiling
    expect(extractMileage("600,000 mi")).toBeUndefined();
  });
  it("rejects tiny values (phone numbers etc)", () => {
    expect(extractMileage("50 miles per gallon")).toBeUndefined();
  });
  it("returns undefined on no mileage", () => {
    expect(extractMileage("clean title")).toBeUndefined();
  });
});

describe("extractCityState", () => {
  it("prefers the 'Listed in ...' phrase", () => {
    expect(
      extractCityState("Listed in Tampa, FL · 10 mi"),
    ).toEqual({ city: "Tampa", state: "FL" });
  });
  it("falls back to any City, ST match", () => {
    expect(
      extractCityState("Nice car in Austin, TX, low miles"),
    ).toEqual({ city: "Austin", state: "TX" });
  });
  it("returns undefined when nothing matches", () => {
    expect(extractCityState("Nice car")).toBeUndefined();
  });
});

describe("upgradeImageUrl", () => {
  it("rewrites _s -> _n", () => {
    expect(upgradeImageUrl("https://scontent.fb/abc_s.jpg")).toBe(
      "https://scontent.fb/abc_n.jpg",
    );
  });
  it("rewrites _t -> _n", () => {
    expect(upgradeImageUrl("https://scontent.fb/abc_t.jpg")).toBe(
      "https://scontent.fb/abc_n.jpg",
    );
  });
  it("leaves unrelated URLs alone", () => {
    const u = "https://scontent.fb/abc_n.jpg";
    expect(upgradeImageUrl(u)).toBe(u);
  });
});

describe("graphRecordToIngest", () => {
  const baseRecord = {
    id: "1234567890",
    marketplace_listing_title: "2018 Ford F-150 XLT",
    listing_price: {
      amount: "22500",
      amount_with_offset_in_currency: "22500",
      formatted_amount: "$22,500",
    },
    primary_listing_photo: {
      image: { uri: "https://scontent.fb/primary.jpg" },
    },
    listing_photos: [
      { image: { uri: "https://scontent.fb/photo1.jpg" } },
      { image: { uri: "https://scontent.fb/photo2.jpg" } },
    ],
    odometer_data: { value: 85000 },
    creation_time: 1_700_000_000,
    location: {
      reverse_geocode: { city: "Tampa", state: "FL" },
    },
    redacted_description: "One owner, clean title, 85k miles, non-smoker.",
  };

  it("maps the full shape", () => {
    const ingest = graphRecordToIngest({ ...baseRecord });
    expect(ingest).toMatchObject({
      source: "facebook_marketplace",
      external_id: "1234567890",
      url: "https://www.facebook.com/marketplace/item/1234567890",
      title: "2018 Ford F-150 XLT",
      year: 2018,
      price: 22500,
      mileage: 85000,
      city: "Tampa",
      state: "FL",
    });
    expect(ingest?.images).toContain("https://scontent.fb/primary.jpg");
    expect(ingest?.images).toContain("https://scontent.fb/photo1.jpg");
    expect(ingest?.posted_at).toMatch(/^2023-/);
    expect(ingest?.description).toMatch(/one owner/i);
  });

  it("handles missing odometer gracefully", () => {
    const rec = { ...baseRecord, odometer_data: undefined };
    const ingest = graphRecordToIngest(rec);
    expect(ingest?.mileage).toBeUndefined();
  });

  it("rejects non-numeric ids", () => {
    expect(
      graphRecordToIngest({ ...baseRecord, id: "not-a-number" }),
    ).toBeNull();
  });

  it("rejects records with no id", () => {
    const rec = { ...baseRecord };
    delete (rec as Partial<typeof baseRecord>).id;
    expect(graphRecordToIngest(rec)).toBeNull();
  });

  it("prefers reverse_geocode_detailed over reverse_geocode", () => {
    const rec = {
      ...baseRecord,
      location: {
        reverse_geocode: { city: "Unused", state: "XX" },
        reverse_geocode_detailed: { city: "Orlando", state: "FL" },
      },
    };
    const ingest = graphRecordToIngest(rec);
    expect(ingest?.city).toBe("Orlando");
  });
});

describe("walkForListingRecords", () => {
  it("finds a nested listing inside a GraphQL payload", () => {
    const payload = {
      data: {
        viewer: {
          marketplace_feed_stories: {
            edges: [
              {
                node: {
                  story: {
                    attachments: [
                      {
                        target: {
                          id: "9999888877776666",
                          marketplace_listing_title: "2019 Honda Civic Sport",
                          listing_price: { amount: 18500 },
                        },
                      },
                    ],
                  },
                },
              },
            ],
          },
        },
      },
    };
    const records = walkForListingRecords(payload);
    expect(records.length).toBe(1);
    expect(records[0].id).toBe("9999888877776666");
  });

  it("handles cycles without crashing", () => {
    const obj: Record<string, unknown> = {};
    obj.self = obj;
    // Should not infinite-loop.
    expect(() => walkForListingRecords(obj)).not.toThrow();
  });

  it("returns empty for unrelated payloads", () => {
    expect(walkForListingRecords({ hello: "world" })).toEqual([]);
  });
});

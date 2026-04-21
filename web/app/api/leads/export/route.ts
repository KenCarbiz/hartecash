import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const forward = new URL(req.url);
  const params = forward.searchParams;
  const url = new URL(`${BASE_URL}/leads/export.csv`);
  for (const [k, v] of params.entries()) {
    url.searchParams.set(k, v);
  }

  const cookieStore = await cookies();
  const session = cookieStore.get("autocurb_session");
  const headers: Record<string, string> = { Accept: "text/csv" };
  if (session) {
    headers["Cookie"] = `autocurb_session=${session.value}`;
  } else {
    headers["X-Dealer-Id"] = "demo-dealer";
  }

  const upstream = await fetch(url.toString(), { headers, cache: "no-store" });
  if (!upstream.ok || !upstream.body) {
    return NextResponse.json(
      { error: `upstream ${upstream.status}` },
      { status: upstream.status },
    );
  }

  const res = new NextResponse(upstream.body, { status: 200 });
  res.headers.set("content-type", "text/csv");
  const disp = upstream.headers.get("content-disposition");
  if (disp) res.headers.set("content-disposition", disp);
  return res;
}

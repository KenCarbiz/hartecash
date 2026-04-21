import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Routes that don't require auth.
const PUBLIC_PREFIXES = [
  "/login",
  "/register",
  "/invite",
  "/_next",
  "/favicon",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public routes pass through.
  for (const prefix of PUBLIC_PREFIXES) {
    if (pathname.startsWith(prefix)) {
      return NextResponse.next();
    }
  }

  // No session cookie -> redirect to login.
  const session = request.cookies.get("autocurb_session");
  if (!session) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Run on every page except Next.js internals + static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};

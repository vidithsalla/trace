import { NextRequest, NextResponse } from "next/server";

// CSRF defence in depth: browsers attach an Origin header to cross-site POSTs. Any state-changing
// /api request whose Origin is not this site is rejected before it reaches the API.
export function middleware(request: NextRequest) {
  if (request.method === "GET" || request.method === "HEAD" || request.method === "OPTIONS") {
    return NextResponse.next();
  }
  const origin = request.headers.get("origin");
  if (origin) {
    let originHost: string | null = null;
    try {
      originHost = new URL(origin).host;
    } catch {
      originHost = null;
    }
    const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
    if (!originHost || originHost !== host) {
      return NextResponse.json({ detail: { code: "CROSS_ORIGIN_REJECTED" } }, { status: 403 });
    }
  }
  return NextResponse.next();
}

export const config = { matcher: "/api/:path*" };

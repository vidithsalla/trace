import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.TRACE_WEB_API_URL ?? "http://localhost:8000";
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
// Only V3 evidence-review routes are reachable through this proxy.
const ALLOWED = new RegExp(
  `^matters/${UUID}(/(analyses|claims|changes|spans|sources|packets|documents)(/[A-Za-z0-9._-]+)*)?$`,
);
const FORWARD_HEADERS = ["content-type", "cookie", "idempotency-key", "x-trace-request"];

async function proxy(request: NextRequest, path: string[]) {
  const joined = path.join("/");
  // Reject dot segments: "a/../b" would match the pattern but normalize outside it.
  if (path.some((segment) => segment === "." || segment === "..") || !ALLOWED.test(joined)) {
    return NextResponse.json({ detail: { code: "NOT_FOUND" } }, { status: 404 });
  }
  const headers = new Headers();
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const search = request.nextUrl.search;
  const upstream = await fetch(`${API_BASE_URL}/${joined}${search}`, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });
  const out = new Headers();
  for (const name of ["content-type", "content-disposition", "set-cookie"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  out.set("x-content-type-options", "nosniff");
  return new NextResponse(upstream.status === 204 ? null : await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: out,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: Ctx) {
  return proxy(request, (await params).path);
}

export async function POST(request: NextRequest, { params }: Ctx) {
  return proxy(request, (await params).path);
}

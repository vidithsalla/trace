import { NextRequest } from "next/server";

import { proxyApiBinaryRequest } from "@/lib/api-proxy";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  return proxyApiBinaryRequest(request, `/audit/export.csv${query}`);
}

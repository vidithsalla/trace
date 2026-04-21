import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  return proxyApiRequest(request, `/audit${query}`);
}

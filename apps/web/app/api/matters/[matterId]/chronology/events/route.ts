import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ matterId: string }> },
) {
  const { matterId } = await params;
  const url = new URL(request.url);
  return proxyApiRequest(request, `/matters/${matterId}/chronology/events${url.search}`);
}

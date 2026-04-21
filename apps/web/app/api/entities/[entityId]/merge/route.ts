import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ entityId: string }> },
) {
  const { entityId } = await params;
  return proxyApiRequest(request, `/entities/${entityId}/merge`);
}

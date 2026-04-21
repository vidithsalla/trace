import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ eventId: string }> },
) {
  const { eventId } = await params;
  return proxyApiRequest(request, `/events/${eventId}`);
}

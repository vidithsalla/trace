import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ matterId: string }> },
) {
  const { matterId } = await params;
  return proxyApiRequest(request, `/matters/${matterId}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ matterId: string }> },
) {
  const { matterId } = await params;
  return proxyApiRequest(request, `/matters/${matterId}`);
}

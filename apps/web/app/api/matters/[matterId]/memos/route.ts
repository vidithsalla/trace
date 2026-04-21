import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ matterId: string }> },
) {
  const { matterId } = await params;
  return proxyApiRequest(request, `/matters/${matterId}/memos`);
}

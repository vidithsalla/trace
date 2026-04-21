import { NextRequest } from "next/server";

import { proxyApiBinaryRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ exportId: string }> },
) {
  const { exportId } = await params;
  return proxyApiBinaryRequest(request, `/exports/${exportId}/download`);
}

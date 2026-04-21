import { NextRequest } from "next/server";

import { proxyApiBinaryRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ documentId: string }> },
) {
  const { documentId } = await params;
  return proxyApiBinaryRequest(request, `/documents/${documentId}/file`);
}

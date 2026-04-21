import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ documentId: string; pageNumber: string }> },
) {
  const { documentId, pageNumber } = await params;
  return proxyApiRequest(request, `/documents/${documentId}/pages/${pageNumber}`);
}

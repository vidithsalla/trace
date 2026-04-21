import { NextRequest } from "next/server";

import { proxyApiBinaryRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ matterId: string }> },
) {
  const { matterId } = await params;
  return proxyApiBinaryRequest(request, `/matters/${matterId}/chronology/export.docx`);
}

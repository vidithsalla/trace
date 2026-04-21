import { NextRequest } from "next/server";

import { proxyApiBinaryRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memoId: string }> },
) {
  const { memoId } = await params;
  return proxyApiBinaryRequest(request, `/memos/${memoId}/export.docx`);
}

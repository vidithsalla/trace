import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memoId: string }> },
) {
  const { memoId } = await params;
  return proxyApiRequest(request, `/memos/${memoId}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ memoId: string }> },
) {
  const { memoId } = await params;
  return proxyApiRequest(request, `/memos/${memoId}`);
}

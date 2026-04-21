import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function POST(request: NextRequest) {
  return proxyApiRequest(request, "/auth/login");
}

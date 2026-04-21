import { NextRequest } from "next/server";

import { proxyApiRequest } from "@/lib/api-proxy";

export async function GET(request: NextRequest) {
  return proxyApiRequest(request, "/matters");
}

export async function POST(request: NextRequest) {
  return proxyApiRequest(request, "/matters");
}

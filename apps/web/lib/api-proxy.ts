import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.TRACE_WEB_API_URL ?? "http://localhost:8000";

export async function proxyApiRequest(
  request: NextRequest,
  path: string,
  init: { method?: string; body?: BodyInit | null } = {},
) {
  const method = init.method ?? request.method;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const cookie = request.headers.get("cookie");

  if (contentType) {
    headers.set("content-type", contentType);
  }
  if (cookie) {
    headers.set("cookie", cookie);
  }

  const body =
    init.body === undefined && method !== "GET" ? await request.arrayBuffer() : init.body;

  const upstream = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  const setCookie = upstream.headers.get("set-cookie");
  const upstreamContentType = upstream.headers.get("content-type");

  if (setCookie) {
    responseHeaders.set("set-cookie", setCookie);
  }
  if (upstreamContentType) {
    responseHeaders.set("content-type", upstreamContentType);
  }

  const responseBody =
    upstream.status === 204 || upstream.status === 304 ? null : await upstream.text();

  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function proxyApiBinaryRequest(request: NextRequest, path: string) {
  const headers = new Headers();
  const cookie = request.headers.get("cookie");
  if (cookie) {
    headers.set("cookie", cookie);
  }

  const upstream = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  const setCookie = upstream.headers.get("set-cookie");
  const contentType = upstream.headers.get("content-type");
  const contentDisposition = upstream.headers.get("content-disposition");
  const exportId = upstream.headers.get("x-trace-export-id");

  if (setCookie) {
    responseHeaders.set("set-cookie", setCookie);
  }
  if (contentType) {
    responseHeaders.set("content-type", contentType);
  }
  if (contentDisposition) {
    responseHeaders.set("content-disposition", contentDisposition);
  }
  if (exportId) {
    responseHeaders.set("x-trace-export-id", exportId);
  }

  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

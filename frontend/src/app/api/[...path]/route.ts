import { NextRequest, NextResponse } from "next/server";

const API_SERVER_BASE =
  process.env.API_SERVER_BASE ?? "http://localhost:8000";

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const backendPath = `/${path.join("/")}`;
  const url = `${API_SERVER_BASE}${backendPath}`;

  const headers = new Headers(req.headers);
  headers.delete("host");

  try {
    const res = await fetch(url, {
      method: req.method,
      headers,
      body: req.body,
      // @ts-expect-error -- duplex required for streaming request bodies in Node 18+
      duplex: "half",
    });

    const body = await res.arrayBuffer();

    return new NextResponse(body, {
      status: res.status,
      statusText: res.statusText,
      headers: res.headers,
    });
  } catch {
    return NextResponse.json(
      { error: "Backend unavailable" },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

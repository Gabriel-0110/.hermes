import { NextResponse } from "next/server";

const HERMES_API = process.env.HERMES_API_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${HERMES_API}/api/v1/portfolio/`, {
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to fetch portfolio", detail: String(error) },
      { status: 502 }
    );
  }
}

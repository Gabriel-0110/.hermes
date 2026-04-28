import { NextResponse } from "next/server";

const HERMES_API = process.env.HERMES_API_URL || "http://localhost:8000";

export async function GET() {
  try {
    const [execRes, eventsRes, movementsRes] = await Promise.all([
      fetch(`${HERMES_API}/api/v1/execution/`, { cache: "no-store" }),
      fetch(`${HERMES_API}/api/v1/execution/events`, { cache: "no-store" }),
      fetch(`${HERMES_API}/api/v1/execution/movements`, { cache: "no-store" }),
    ]);
    const [exec, events, movements] = await Promise.all([
      execRes.json(),
      eventsRes.json(),
      movementsRes.json(),
    ]);
    return NextResponse.json({ ...exec, events: events.events || [], movements: movements.movements || [] });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to fetch execution", detail: String(error) },
      { status: 502 }
    );
  }
}

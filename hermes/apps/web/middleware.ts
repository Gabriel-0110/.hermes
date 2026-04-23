import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (
    process.env.HERMES_MISSION_CONTROL_HOME === "true" &&
    request.nextUrl.pathname === "/"
  ) {
    return NextResponse.redirect(new URL("/mission-control", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/"],
};
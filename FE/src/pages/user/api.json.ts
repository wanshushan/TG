import type { APIRoute } from "astro";
import { resolveUserDashboardData } from "../../lib/user-profile";

export const GET: APIRoute = async ({ request }) => {
    const result = await resolveUserDashboardData(fetch, {
        cookieHeader: request.headers.get("cookie") || "",
        requestOrigin: new URL(request.url).origin,
        internalOrigin: process.env.FE_INTERNAL_ORIGIN || "http://127.0.0.1:4321",
    });

    return new Response(
        JSON.stringify({
            source: result.source,
            isLoggedIn: result.isLoggedIn,
            ...result.profile,
            charts: result.charts,
            authMessage: result.authMessage,
            error: result.error,
        }),
        {
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
            },
        },
    );
};

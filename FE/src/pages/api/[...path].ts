import type { APIRoute } from "astro";

const DEFAULT_RD_BACKEND_BASE_URL = "http://127.0.0.1:3000";

function getBackendBaseUrl(): string {
    const configured =
        process.env.RD_BACKEND_BASE_URL ||
        process.env.PUBLIC_RD_BACKEND_BASE_URL ||
        DEFAULT_RD_BACKEND_BASE_URL;
    return configured.trim().replace(/\/$/, "") || DEFAULT_RD_BACKEND_BASE_URL;
}

function buildUpstreamUrl(requestUrl: URL): string {
    return `${getBackendBaseUrl()}${requestUrl.pathname}${requestUrl.search}`;
}

function getOriginFromUrl(url: string): string | null {
    try {
        return new URL(url).origin;
    } catch {
        return null;
    }
}

function copyRequestHeaders(source: Headers): Headers {
    const headers = new Headers();
    for (const [key, value] of source.entries()) {
        const lower = key.toLowerCase();
        if (
            lower === "host" ||
            lower === "content-length" ||
            lower === "origin" ||
            lower === "referer" ||
            lower.startsWith("sec-fetch-")
        ) {
            continue;
        }
        headers.set(key, value);
    }
    return headers;
}

async function proxyRequest(context: Parameters<APIRoute>[0]): Promise<Response> {
    const { request } = context;
    const method = request.method.toUpperCase();
    const upstreamUrl = buildUpstreamUrl(new URL(request.url));
    const upstreamOrigin = getOriginFromUrl(upstreamUrl);

    const headers = copyRequestHeaders(request.headers);

    if (upstreamOrigin) {
        headers.set("origin", upstreamOrigin);
        headers.set("referer", `${upstreamOrigin}/`);
    }

    const hasBody = !["GET", "HEAD"].includes(method);
    const body = hasBody ? await request.arrayBuffer() : undefined;
    const upstreamResponse = await fetch(upstreamUrl, {
        method,
        headers,
        body,
        redirect: "manual",
    });

    const responseHeaders = new Headers(upstreamResponse.headers);
    responseHeaders.delete("content-length");

    const setCookie = upstreamResponse.headers.get("set-cookie");
    if (setCookie) {
        responseHeaders.set("set-cookie", setCookie);
    }

    return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
    });
}

export const GET: APIRoute = proxyRequest;
export const POST: APIRoute = proxyRequest;
export const PUT: APIRoute = proxyRequest;
export const PATCH: APIRoute = proxyRequest;
export const DELETE: APIRoute = proxyRequest;
export const OPTIONS: APIRoute = proxyRequest;
export const HEAD: APIRoute = proxyRequest;

import type { APIRoute } from "astro";
import config from "./api.json";

type ModelOptionInput =
    | string
    | {
        name?: string;
        label?: string;
        model?: string;
        apiEndpoint?: string;
        systemPrompt?: string;
    };

type PublicModelOption = {
    name: string;
    model: string;
    apiEndpoint: string;
    systemPrompt?: string;
};

type ConfigShape = {
    apiEndpoint?: string;
    model?: string;
    selectedOptionName?: string;
    modelOptions?: ModelOptionInput[];
    systemPrompt?: string;
    exampleApiEndpoint?: string;
};

function normalizeApiEndpoint(endpoint: string): string {
    const trimmed = endpoint.trim();
    if (/^https:\/\/api\.deepseek\.com\/?$/i.test(trimmed)) {
        return "https://api.deepseek.com/chat/completions";
    }
    return trimmed;
}

function normalizePublicModelOptions(
    options: ModelOptionInput[],
    fallback: { apiEndpoint: string; model: string; systemPrompt: string },
): PublicModelOption[] {
    const normalized: PublicModelOption[] = [];

    for (const option of options) {
        if (typeof option === "string") {
            const value = option.trim();
            if (!value) {
                continue;
            }
            normalized.push({
                name: value,
                model: value,
                apiEndpoint: fallback.apiEndpoint,
                systemPrompt: fallback.systemPrompt,
            });
            continue;
        }

        if (!option || typeof option !== "object") {
            continue;
        }

        const model = (option.model || "").trim();
        const name = (option.name || option.label || model).trim();
        const apiEndpoint = normalizeApiEndpoint(
            (option.apiEndpoint || fallback.apiEndpoint).trim(),
        );

        if (!name || !model || !apiEndpoint) {
            continue;
        }

        normalized.push({
            name,
            model,
            apiEndpoint,
            systemPrompt: (option.systemPrompt ?? fallback.systemPrompt).trim(),
        });
    }

    const dedup = new Map<string, PublicModelOption>();
    for (const item of normalized) {
        if (!dedup.has(item.name)) {
            dedup.set(item.name, item);
        }
    }

    const result = Array.from(dedup.values());
    if (result.length === 0 && fallback.model && fallback.apiEndpoint) {
        result.push({
            name: fallback.model,
            model: fallback.model,
            apiEndpoint: fallback.apiEndpoint,
            systemPrompt: fallback.systemPrompt,
        });
    }

    return result;
}

export const GET: APIRoute = () => {
    const raw = config as ConfigShape;
    const fallbackApiEndpoint = normalizeApiEndpoint(
        (raw.apiEndpoint || "").trim(),
    );
    const fallbackModel = (raw.model || "").trim();
    const fallbackSystemPrompt = (raw.systemPrompt || "").trim();

    const publicConfig = {
        apiEndpoint: fallbackApiEndpoint,
        model: fallbackModel,
        selectedOptionName: (raw.selectedOptionName || "").trim(),
        modelOptions: normalizePublicModelOptions(
            Array.isArray(raw.modelOptions) ? raw.modelOptions : [],
            {
                apiEndpoint: fallbackApiEndpoint,
                model: fallbackModel,
                systemPrompt: fallbackSystemPrompt,
            },
        ),
        systemPrompt: fallbackSystemPrompt,
        exampleApiEndpoint: (raw.exampleApiEndpoint || "").trim(),
    };

    return new Response(JSON.stringify(publicConfig), {
        headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
    });
};

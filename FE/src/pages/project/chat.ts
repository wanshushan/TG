import type { APIRoute } from "astro";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import * as path from "node:path";
import config from "./api.json";

type ChatMessage = {
    role: "system" | "user" | "assistant";
    content: string;
};

type ModelOptionInput =
    | string
    | {
        name?: string;
        label?: string;
        model?: string;
        apiEndpoint?: string;
        apiKey?: string;
        apiKeyEnv?: string;
        systemPrompt?: string;
    };

type ModelOptionConfig = {
    name: string;
    model: string;
    apiEndpoint: string;
    apiKey: string;
    apiKeyEnv: string;
    systemPrompt: string;
};

type ConfigShape = {
    apiEndpoint?: string;
    apiKey?: string;
    apiKeyEnv?: string;
    model?: string;
    selectedOptionName?: string;
    modelOptions?: ModelOptionInput[];
    systemPrompt?: string;
};

type PersistMessage = {
    role: "user" | "assistant";
    content: string;
};

function resolveChatRecordsDir(): string {
    const cwd = process.cwd();
    const cwdName = path.basename(cwd).toLowerCase();
    if (cwdName === "fe") {
        return path.resolve(cwd, "../RD/chat");
    }
    return path.resolve(cwd, "RD/chat");
}

const CHAT_RECORDS_DIR = resolveChatRecordsDir();
const CHAT_RECORD_NAME_PATTERN = /^\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?:-\d+)?$/;
const SAFE_RECORD_BASENAME_PATTERN = /^\d{2}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d+)?$/;

function jsonResponse(payload: unknown, status = 200): Response {
    return new Response(JSON.stringify(payload), {
        status,
        headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
    });
}

function pad2(value: number): string {
    return String(value).padStart(2, "0");
}

function formatRecordName(date = new Date()): string {
    const year = pad2(date.getFullYear() % 100);
    const month = pad2(date.getMonth() + 1);
    const day = pad2(date.getDate());
    const hour = pad2(date.getHours());
    const minute = pad2(date.getMinutes());
    return `${year}-${month}-${day}T${hour}:${minute}`;
}

function recordNameToSafeBasename(recordName: string): string {
    return recordName.replace(":", "-");
}

function safeBasenameToRecordName(fileBaseName: string): string | null {
    if (CHAT_RECORD_NAME_PATTERN.test(fileBaseName)) {
        return fileBaseName;
    }

    if (!SAFE_RECORD_BASENAME_PATTERN.test(fileBaseName)) {
        return null;
    }

    const match = fileBaseName.match(
        /^(\d{2}-\d{2}-\d{2}T\d{2})-(\d{2})(-\d+)?$/,
    );
    if (!match) {
        return null;
    }

    return `${match[1]}:${match[2]}${match[3] ?? ""}`;
}

async function ensureChatRecordsDir() {
    await mkdir(CHAT_RECORDS_DIR, { recursive: true });
}

async function listRecordNames(): Promise<string[]> {
    await ensureChatRecordsDir();
    const entries = await readdir(CHAT_RECORDS_DIR, { withFileTypes: true });
    return entries
        .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".md"))
        .map((entry) => entry.name.slice(0, -3))
        .map((fileBaseName) => safeBasenameToRecordName(fileBaseName))
        .filter((name): name is string => Boolean(name))
        .sort((a, b) => (a === b ? 0 : a > b ? -1 : 1));
}

function sanitizeRecordName(rawName?: string): string | null {
    const name = (rawName || "").trim();
    if (!name) {
        return null;
    }
    if (!CHAT_RECORD_NAME_PATTERN.test(name)) {
        return null;
    }
    return name;
}

async function buildUniqueRecordName(): Promise<string> {
    const baseName = formatRecordName();
    const existingNames = new Set(await listRecordNames());
    if (!existingNames.has(baseName)) {
        return baseName;
    }

    let suffix = 1;
    while (true) {
        const suffixText = suffix <= 99 ? pad2(suffix) : String(suffix);
        const candidate = `${baseName}-${suffixText}`;
        if (!existingNames.has(candidate)) {
            return candidate;
        }
        suffix += 1;
    }
}

function normalizePersistMessages(messages: unknown): PersistMessage[] {
    if (!Array.isArray(messages)) {
        return [];
    }

    const normalized: PersistMessage[] = [];
    for (const message of messages) {
        if (!message || typeof message !== "object") {
            continue;
        }
        const role = (message as { role?: unknown }).role;
        const content = (message as { content?: unknown }).content;
        if ((role === "user" || role === "assistant") && typeof content === "string") {
            if (content.trim()) {
                normalized.push({ role, content });
            }
        }
    }

    return normalized;
}

function serializeRecordMarkdown(
    recordName: string,
    messages: PersistMessage[],
): string {
    return [
        `# 对话记录 ${recordName}`,
        "",
        `更新时间：${new Date().toISOString()}`,
        "",
        "```json",
        JSON.stringify(messages, null, 2),
        "```",
        "",
    ].join("\n");
}

function parseRecordMarkdown(markdown: string): PersistMessage[] {
    const match = markdown.match(/```json\s*([\s\S]*?)\s*```/i);
    if (!match) {
        return [];
    }

    try {
        return normalizePersistMessages(JSON.parse(match[1]));
    } catch {
        return [];
    }
}

export const GET: APIRoute = async ({ url }) => {
    try {
        const action = (url.searchParams.get("action") || "list").trim();

        if (action === "list") {
            const records = await listRecordNames();
            return jsonResponse({ records });
        }

        if (action === "load") {
            const name = sanitizeRecordName(url.searchParams.get("name") || "");
            if (!name) {
                return jsonResponse(
                    { error: "name 参数无效，格式应为 yy-mm-ddThh:mm" },
                    400,
                );
            }

            let markdown = "";
            const candidatePaths = [
                path.join(CHAT_RECORDS_DIR, `${recordNameToSafeBasename(name)}.md`),
                path.join(CHAT_RECORDS_DIR, `${name}.md`),
            ];

            let readSucceeded = false;
            for (const candidatePath of candidatePaths) {
                try {
                    markdown = await readFile(candidatePath, "utf-8");
                    readSucceeded = true;
                    break;
                } catch {
                    continue;
                }
            }

            if (!readSucceeded) {
                return jsonResponse({ error: "记录不存在" }, 404);
            }

            const messages = parseRecordMarkdown(markdown);
            return jsonResponse({
                recordName: name,
                messages,
            });
        }

        return jsonResponse({ error: "不支持的 action 参数" }, 400);
    } catch (error) {
        return jsonResponse(
            {
                error: `读取对话记录失败：${error instanceof Error ? error.message : String(error)}`,
            },
            500,
        );
    }
};

export const PUT: APIRoute = async ({ request }) => {
    try {
        const body = (await request.json()) as {
            recordName?: string;
            messages?: unknown;
        };

        const messages = normalizePersistMessages(body.messages);
        if (messages.length === 0) {
            return jsonResponse({ error: "messages 不能为空" }, 400);
        }

        const providedRecordName = (body.recordName || "").trim();
        const sanitizedRecordName = sanitizeRecordName(providedRecordName);
        if (providedRecordName && !sanitizedRecordName) {
            return jsonResponse(
                { error: "recordName 参数无效，格式应为 yy-mm-ddThh:mm" },
                400,
            );
        }

        const recordName = sanitizedRecordName || (await buildUniqueRecordName());
        const filePath = path.join(
            CHAT_RECORDS_DIR,
            `${recordNameToSafeBasename(recordName)}.md`,
        );
        const markdown = serializeRecordMarkdown(recordName, messages);

        await ensureChatRecordsDir();
        await writeFile(filePath, markdown, "utf-8");

        return jsonResponse({
            recordName,
            records: await listRecordNames(),
        });
    } catch (error) {
        return jsonResponse(
            {
                error: `保存对话记录失败：${error instanceof Error ? error.message : String(error)}`,
            },
            500,
        );
    }
};

function isOllamaEndpoint(endpoint: string): boolean {
    return (
        endpoint.includes("127.0.0.1:11434") ||
        endpoint.includes("localhost:11434")
    );
}

function extractModelNotFound(errorText: string): string | null {
    const match = errorText.match(/model '([^']+)' not found/i);
    return match?.[1] ?? null;
}

function findBestOllamaModel(
    requestedModel: string,
    candidates: string[],
): string | null {
    if (!requestedModel || candidates.length === 0) {
        return null;
    }

    const requestedLower = requestedModel.toLowerCase();
    const exact = candidates.find(
        (candidate) => candidate.toLowerCase() === requestedLower,
    );
    if (exact) {
        return exact;
    }

    const prefix = candidates.find((candidate) =>
        candidate.toLowerCase().startsWith(requestedLower),
    );
    if (prefix) {
        return prefix;
    }

    const family = requestedLower.split(":")[0];
    const familyMatch = candidates.find((candidate) =>
        candidate.toLowerCase().startsWith(`${family}:`),
    );
    if (familyMatch) {
        return familyMatch;
    }

    return null;
}

async function resolveOllamaModelName(
    apiEndpoint: string,
    requestedModel: string,
): Promise<string | null> {
    try {
        const endpoint = new URL(apiEndpoint);
        const tagsEndpoint = `${endpoint.protocol}//${endpoint.host}/api/tags`;
        const tagsResponse = await fetch(tagsEndpoint, {
            method: "GET",
            headers: {
                "Cache-Control": "no-store",
            },
        });

        if (!tagsResponse.ok) {
            return null;
        }

        const payload = (await tagsResponse.json()) as {
            models?: Array<{ name?: string; model?: string }>;
        };
        const modelNames = (payload.models || [])
            .map((item) => (item.name || item.model || "").trim())
            .filter((name) => name.length > 0);

        return findBestOllamaModel(requestedModel, modelNames);
    } catch {
        return null;
    }
}

function normalizeApiEndpoint(endpoint: string): string {
    const trimmed = endpoint.trim();
    if (/^https:\/\/api\.deepseek\.com\/?$/i.test(trimmed)) {
        return "https://api.deepseek.com/chat/completions";
    }
    return trimmed;
}

function normalizeModelOptions(
    options: ModelOptionInput[],
    fallback: {
        apiEndpoint: string;
        apiKey: string;
        apiKeyEnv: string;
        model: string;
        systemPrompt: string;
    },
): ModelOptionConfig[] {
    const normalized: ModelOptionConfig[] = [];

    for (const option of options) {
        if (typeof option === "string") {
            const value = option.trim();
            if (!value) {
                continue;
            }
            normalized.push({
                name: value,
                model: value,
                apiEndpoint: normalizeApiEndpoint(fallback.apiEndpoint),
                apiKey: fallback.apiKey,
                apiKeyEnv: fallback.apiKeyEnv,
                systemPrompt: fallback.systemPrompt,
            });
            continue;
        }

        if (!option || typeof option !== "object") {
            continue;
        }

        const optionModel = (option.model || "").trim();
        const optionName = (option.name || option.label || optionModel).trim();
        const optionEndpoint = normalizeApiEndpoint(
            (option.apiEndpoint || fallback.apiEndpoint).trim(),
        );

        if (!optionName || !optionModel || !optionEndpoint) {
            continue;
        }

        normalized.push({
            name: optionName,
            model: optionModel,
            apiEndpoint: optionEndpoint,
            apiKey: (option.apiKey ?? fallback.apiKey).trim(),
            apiKeyEnv: (option.apiKeyEnv ?? fallback.apiKeyEnv).trim(),
            systemPrompt: (option.systemPrompt ?? fallback.systemPrompt).trim(),
        });
    }

    const dedup = new Map<string, ModelOptionConfig>();
    for (const item of normalized) {
        if (!dedup.has(item.name)) {
            dedup.set(item.name, item);
        }
    }

    const result = Array.from(dedup.values());
    if (
        result.length === 0 &&
        fallback.model &&
        normalizeApiEndpoint(fallback.apiEndpoint)
    ) {
        result.push({
            name: fallback.model,
            model: fallback.model,
            apiEndpoint: normalizeApiEndpoint(fallback.apiEndpoint),
            apiKey: fallback.apiKey,
            apiKeyEnv: fallback.apiKeyEnv,
            systemPrompt: fallback.systemPrompt,
        });
    }

    return result;
}

function getResolvedOption(rawConfig: ConfigShape, selectedOptionName?: string) {
    const fallbackApiEndpoint = normalizeApiEndpoint(
        (rawConfig.apiEndpoint || "").trim(),
    );
    const fallbackApiKey = (rawConfig.apiKey || "").trim();
    const fallbackApiKeyEnv = (rawConfig.apiKeyEnv || "").trim();
    const fallbackModel = (rawConfig.model || "").trim();
    const fallbackSystemPrompt = (rawConfig.systemPrompt || "").trim();

    const modelOptions = normalizeModelOptions(
        Array.isArray(rawConfig.modelOptions) ? rawConfig.modelOptions : [],
        {
            apiEndpoint: fallbackApiEndpoint,
            apiKey: fallbackApiKey,
            apiKeyEnv: fallbackApiKeyEnv,
            model: fallbackModel,
            systemPrompt: fallbackSystemPrompt,
        },
    );

    const preferredName = (selectedOptionName || "").trim();
    const configSelectedName = (rawConfig.selectedOptionName || "").trim();

    const resolved =
        modelOptions.find((option) => option.name === preferredName) ||
        modelOptions.find((option) => option.name === configSelectedName) ||
        modelOptions[0];

    return {
        resolved,
        modelOptions,
    };
}

function resolveApiKey(apiKeyEnv: string, apiKey: string): string {
    const envName = apiKeyEnv.trim();
    if (envName) {
        const viteEnvValue = (
            import.meta.env as Record<string, string | undefined>
        )[envName];
        if (typeof viteEnvValue === "string" && viteEnvValue.trim()) {
            return viteEnvValue.trim();
        }

        const processEnvValue = process.env[envName];
        if (typeof processEnvValue === "string" && processEnvValue.trim()) {
            return processEnvValue.trim();
        }
    }
    return apiKey.trim();
}

export const POST: APIRoute = async ({ request }) => {
    try {
        const body = (await request.json()) as {
            selectedOptionName?: string;
            messages?: ChatMessage[];
            stream?: boolean;
        };

        const messages = Array.isArray(body.messages) ? body.messages : [];
        if (messages.length === 0) {
            return new Response(
                JSON.stringify({ error: "messages 不能为空" }),
                {
                    status: 400,
                    headers: {
                        "Content-Type": "application/json; charset=utf-8",
                    },
                },
            );
        }

        const { resolved } = getResolvedOption(
            config as ConfigShape,
            body.selectedOptionName,
        );

        if (!resolved || !resolved.apiEndpoint || !resolved.model) {
            return new Response(
                JSON.stringify({ error: "api.json 配置不完整" }),
                {
                    status: 500,
                    headers: {
                        "Content-Type": "application/json; charset=utf-8",
                    },
                },
            );
        }

        const resolvedApiKey = resolveApiKey(
            resolved.apiKeyEnv,
            resolved.apiKey,
        );

        if (resolved.apiKeyEnv && !resolvedApiKey) {
            return new Response(
                JSON.stringify({
                    error: `环境变量 ${resolved.apiKeyEnv} 未设置，请在 .env 中配置后重启服务`,
                }),
                {
                    status: 500,
                    headers: {
                        "Content-Type": "application/json; charset=utf-8",
                    },
                },
            );
        }

        const headers: Record<string, string> = {
            "Content-Type": "application/json",
        };
        if (resolvedApiKey) {
            headers.Authorization = `Bearer ${resolvedApiKey}`;
        }

        const requestStream = body.stream === true;
        const sendToUpstream = async (targetModel: string) => {
            const response = await fetch(resolved.apiEndpoint, {
                method: "POST",
                headers,
                body: JSON.stringify({
                    model: targetModel,
                    messages,
                    stream: requestStream,
                }),
            });

            return response;
        };

        let activeModel = resolved.model;
        let upstreamResponse = await sendToUpstream(activeModel);
        let contentType = upstreamResponse.headers.get("content-type") || "";

        if (!upstreamResponse.ok) {
            const firstErrorText = await upstreamResponse.text();
            const missingModel = extractModelNotFound(firstErrorText);

            if (
                upstreamResponse.status === 404 &&
                missingModel &&
                isOllamaEndpoint(resolved.apiEndpoint)
            ) {
                const retryModel = await resolveOllamaModelName(
                    resolved.apiEndpoint,
                    missingModel,
                );

                if (retryModel && retryModel !== activeModel) {
                    activeModel = retryModel;
                    upstreamResponse = await sendToUpstream(activeModel);
                    contentType =
                        upstreamResponse.headers.get("content-type") || "";
                } else {
                    return new Response(firstErrorText || "上游接口请求失败", {
                        status: upstreamResponse.status,
                        headers: {
                            "Content-Type": contentType.includes("application/json")
                                ? "application/json; charset=utf-8"
                                : "text/plain; charset=utf-8",
                        },
                    });
                }
            } else {
                return new Response(firstErrorText || "上游接口请求失败", {
                    status: upstreamResponse.status,
                    headers: {
                        "Content-Type": contentType.includes("application/json")
                            ? "application/json; charset=utf-8"
                            : "text/plain; charset=utf-8",
                    },
                });
            }
        }

        if (!upstreamResponse.ok) {
            const errorText = await upstreamResponse.text();
            return new Response(errorText || "上游接口请求失败", {
                status: upstreamResponse.status,
                headers: {
                    "Content-Type": contentType.includes("application/json")
                        ? "application/json; charset=utf-8"
                        : "text/plain; charset=utf-8",
                },
            });
        }

        if (contentType.includes("application/json")) {
            const json = await upstreamResponse.json();
            return new Response(JSON.stringify(json), {
                status: 200,
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store",
                    "X-Resolved-Model": activeModel,
                },
            });
        }

        const text = await upstreamResponse.text();
        return new Response(text, {
            status: 200,
            headers: {
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Resolved-Model": activeModel,
            },
        });
    } catch (error) {
        return new Response(
            JSON.stringify({
                error: `请求处理失败：${error instanceof Error ? error.message : String(error)}`,
            }),
            {
                status: 500,
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                },
            },
        );
    }
};

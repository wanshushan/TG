import {
    USER_CHART_DEFINITIONS,
    USER_PROFILE_CONFIG,
    getUserFallbackName,
    type UserApiSourceConfig,
    type UserChartPoint,
    type UserProfile,
    type UserProfileLink,
} from "../config";

export type ResolvedUserProfile = {
    username: string;
    bio: string;
    avatar: string;
    links: UserProfileLink[];
};

export type ResolvedUserChart = {
    id: string;
    title: string;
    xAxisName: string;
    yAxisName: string;
    points: UserChartPoint[];
};

export type UserDashboardResolveResult = {
    source: "file" | "api";
    isLoggedIn: boolean;
    profile: ResolvedUserProfile;
    charts: ResolvedUserChart[];
    error?: string;
    authMessage?: string;
};

export type UserProfileResolveResult = {
    source: "file" | "api";
    isLoggedIn: boolean;
    profile: ResolvedUserProfile;
    error?: string;
    authMessage?: string;
};

type AuthStatusResult = {
    isLoggedIn: boolean;
    username: string;
    message: string;
};

export type ResolveUserDataOptions = {
    cookieHeader?: string;
};

function toNonEmptyString(value: unknown): string {
    return typeof value === "string" ? value.trim() : "";
}

function toFiniteNumber(value: unknown): number | undefined {
    if (typeof value === "number" && Number.isFinite(value)) {
        return value;
    }

    if (typeof value === "string") {
        const numeric = Number(value);
        if (Number.isFinite(numeric)) {
            return numeric;
        }
    }

    return undefined;
}

function toBoolean(value: unknown): boolean {
    if (typeof value === "boolean") {
        return value;
    }

    if (typeof value === "number") {
        return value === 1;
    }

    if (typeof value === "string") {
        const normalized = value.trim().toLowerCase();
        return normalized === "true" || normalized === "1";
    }

    return false;
}

function buildRequestHeaders(cookieHeader?: string): Record<string, string> {
    const headers: Record<string, string> = {
        Accept: "application/json",
    };

    const cookieValue = toNonEmptyString(cookieHeader);
    if (cookieValue) {
        headers.Cookie = cookieValue;
    }

    return headers;
}

function clonePoints(points: UserChartPoint[]): UserChartPoint[] {
    return points.map((point) => ({ x: point.x, y: point.y }));
}

function toIconValue(value: unknown): UserProfileLink["icon"] | undefined {
    if (typeof value !== "string") {
        return undefined;
    }

    const normalized = value.trim();
    if (!/^fa6-(brands|solid|regular):.+$/i.test(normalized)) {
        return undefined;
    }

    return normalized as UserProfileLink["icon"];
}

function normalizeLinks(
    input: unknown,
    fallbackLinks: UserProfileLink[],
): UserProfileLink[] {
    if (!Array.isArray(input)) {
        return fallbackLinks;
    }

    const normalized: UserProfileLink[] = [];

    for (const item of input) {
        if (!item || typeof item !== "object") {
            continue;
        }

        const record = item as Record<string, unknown>;
        const name = toNonEmptyString(record.name);
        const href = toNonEmptyString(record.href);

        if (!name || !href) {
            continue;
        }

        normalized.push({
            name,
            href,
            icon: toIconValue(record.icon),
        });
    }

    if (normalized.length === 0) {
        return fallbackLinks;
    }

    const dedup = new Map<string, UserProfileLink>();
    for (const item of normalized) {
        if (!dedup.has(item.name)) {
            dedup.set(item.name, item);
        }
    }

    return Array.from(dedup.values());
}

function normalizeProfile(raw?: Partial<UserProfile>): ResolvedUserProfile {
    const fallbackName = getUserFallbackName();
    const fileProfile = USER_PROFILE_CONFIG.file;

    return {
        username:
            toNonEmptyString(raw?.username) ||
            toNonEmptyString(fileProfile.username) ||
            fallbackName,
        bio: toNonEmptyString(raw?.bio) || toNonEmptyString(fileProfile.bio),
        avatar:
            toNonEmptyString(raw?.avatar) || toNonEmptyString(fileProfile.avatar),
        links: normalizeLinks(raw?.links, fileProfile.links),
    };
}

function getFieldValue(record: Record<string, unknown>, field: string): unknown {
    if (!field) {
        return undefined;
    }

    const direct = record[field];
    if (direct !== undefined) {
        return direct;
    }

    const dataValue = record.data;
    if (dataValue && typeof dataValue === "object") {
        return (dataValue as Record<string, unknown>)[field];
    }

    return undefined;
}

function normalizeChartPoints(
    input: unknown,
    mapping: UserApiSourceConfig["mapping"],
    fallbackPoints: UserChartPoint[],
): UserChartPoint[] {
    if (!Array.isArray(input)) {
        return clonePoints(fallbackPoints);
    }

    const normalized: UserChartPoint[] = [];

    for (const item of input) {
        if (!item || typeof item !== "object") {
            continue;
        }

        const record = item as Record<string, unknown>;
        const x = toFiniteNumber(record[mapping.pointXField] ?? record.x);
        const y = toFiniteNumber(record[mapping.pointYField] ?? record.y);

        if (x === undefined || y === undefined) {
            continue;
        }

        normalized.push({ x, y });
    }

    if (normalized.length === 0) {
        return clonePoints(fallbackPoints);
    }

    normalized.sort((a, b) => a.x - b.x);
    return normalized;
}

function getChartsFromFile(): ResolvedUserChart[] {
    return USER_CHART_DEFINITIONS.slice(0, 4).map((definition) => ({
        id: definition.id,
        title: definition.title,
        xAxisName: definition.xAxisName,
        yAxisName: definition.yAxisName,
        points: clonePoints(definition.fallbackPoints),
    }));
}

function normalizeChartsFromApi(
    record: Record<string, unknown>,
    mapping: UserApiSourceConfig["mapping"],
): ResolvedUserChart[] {
    const chartMap = new Map<string, UserChartPoint[]>();
    const rawCharts = getFieldValue(record, mapping.chartsField);

    if (Array.isArray(rawCharts)) {
        for (const item of rawCharts) {
            if (!item || typeof item !== "object") {
                continue;
            }

            const chartRecord = item as Record<string, unknown>;
            const chartId = toNonEmptyString(
                chartRecord[mapping.chartIdField] ?? chartRecord.id,
            );
            const points = normalizeChartPoints(
                chartRecord[mapping.chartPointsField] ?? chartRecord.points,
                mapping,
                [],
            );

            if (!chartId || points.length === 0) {
                continue;
            }

            chartMap.set(chartId, points);
        }
    }

    if (rawCharts && typeof rawCharts === "object" && !Array.isArray(rawCharts)) {
        for (const [chartId, chartValue] of Object.entries(
            rawCharts as Record<string, unknown>,
        )) {
            const points = normalizeChartPoints(chartValue, mapping, []);
            if (points.length > 0) {
                chartMap.set(chartId, points);
            }
        }
    }

    return USER_CHART_DEFINITIONS.slice(0, 4).map((definition) => ({
        id: definition.id,
        title: definition.title,
        xAxisName: definition.xAxisName,
        yAxisName: definition.yAxisName,
        points:
            chartMap.get(definition.id) && chartMap.get(definition.id)!.length > 0
                ? clonePoints(chartMap.get(definition.id)!)
                : clonePoints(definition.fallbackPoints),
    }));
}

function extractProfileFromApiRecord(
    record: Record<string, unknown>,
    mapping: UserApiSourceConfig["mapping"],
): ResolvedUserProfile {
    return normalizeProfile({
        username: toNonEmptyString(getFieldValue(record, mapping.usernameField)),
        bio: toNonEmptyString(getFieldValue(record, mapping.bioField)),
        avatar: toNonEmptyString(getFieldValue(record, mapping.avatarField)),
        links: getFieldValue(record, mapping.linksField) as UserProfileLink[],
    });
}

function isBridgeEndpoint(endpoint: string): boolean {
    const normalizedEndpoint = endpoint.trim();
    if (!normalizedEndpoint) {
        return false;
    }

    const bridgePath = USER_PROFILE_CONFIG.bridgeEndpoint.trim() || "/user/api.json";

    const normalizePath = (value: string) => {
        try {
            return new URL(value, "http://127.0.0.1").pathname;
        } catch {
            return value;
        }
    };

    return normalizePath(normalizedEndpoint) === normalizePath(bridgePath);
}

async function fetchAuthStatus(
    fetcher: typeof fetch,
    options: ResolveUserDataOptions = {},
): Promise<AuthStatusResult> {
    const authConfig = USER_PROFILE_CONFIG.auth;
    const endpoint = toNonEmptyString(authConfig.statusEndpoint);
    const fallbackUsername = getUserFallbackName();

    if (!endpoint) {
        return {
            isLoggedIn: false,
            username: fallbackUsername,
            message: "未配置登录状态接口，使用本地数据",
        };
    }

    const controller = new AbortController();
    const timeoutMs =
        Number.isFinite(authConfig.timeoutMs) && authConfig.timeoutMs > 0
            ? authConfig.timeoutMs
            : 5000;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetcher(endpoint, {
            method: "GET",
            headers: buildRequestHeaders(options.cookieHeader),
            credentials: "include",
            signal: controller.signal,
        });

        if (!response.ok) {
            return {
                isLoggedIn: false,
                username: fallbackUsername,
                message: `状态接口响应异常（HTTP ${response.status}）`,
            };
        }

        const payload = (await response.json()) as unknown;
        if (!payload || typeof payload !== "object") {
            return {
                isLoggedIn: false,
                username: fallbackUsername,
                message: "状态接口返回格式非法，使用本地数据",
            };
        }

        const record = payload as Record<string, unknown>;
        const mapping = authConfig.mapping;
        const isLoggedIn = toBoolean(
            getFieldValue(record, mapping.loggedInField),
        );

        return {
            isLoggedIn,
            username:
                toNonEmptyString(getFieldValue(record, mapping.usernameField)) ||
                fallbackUsername,
            message:
                toNonEmptyString(getFieldValue(record, mapping.messageField)) ||
                "",
        };
    } catch (error) {
        return {
            isLoggedIn: false,
            username: fallbackUsername,
            message: `状态接口请求失败，使用本地数据：${error instanceof Error ? error.message : String(error)
                }`,
        };
    } finally {
        clearTimeout(timeoutId);
    }
}

async function fetchDashboardFromApi(
    fetcher: typeof fetch,
    options: ResolveUserDataOptions = {},
): Promise<{ profile: ResolvedUserProfile; charts: ResolvedUserChart[] } | null> {
    const apiConfig = USER_PROFILE_CONFIG.api;
    const endpoint = toNonEmptyString(apiConfig.endpoint);

    if (!endpoint || isBridgeEndpoint(endpoint)) {
        return null;
    }

    const controller = new AbortController();
    const timeoutMs =
        Number.isFinite(apiConfig.timeoutMs) && apiConfig.timeoutMs > 0
            ? apiConfig.timeoutMs
            : 5000;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetcher(endpoint, {
            method: "GET",
            headers: buildRequestHeaders(options.cookieHeader),
            credentials: "include",
            signal: controller.signal,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const payload = (await response.json()) as unknown;
        if (!payload || typeof payload !== "object") {
            throw new Error("API 返回格式不是对象");
        }

        const record = payload as Record<string, unknown>;

        return {
            profile: extractProfileFromApiRecord(record, apiConfig.mapping),
            charts: normalizeChartsFromApi(record, apiConfig.mapping),
        };
    } finally {
        clearTimeout(timeoutId);
    }
}

export function getProfileFromFile(): ResolvedUserProfile {
    return normalizeProfile(USER_PROFILE_CONFIG.file);
}

export function getChartsFromConfig(): ResolvedUserChart[] {
    return getChartsFromFile();
}

export async function resolveUserDashboardData(
    fetcher: typeof fetch = fetch,
    options: ResolveUserDataOptions = {},
): Promise<UserDashboardResolveResult> {
    const fileProfile = getProfileFromFile();
    const fileCharts = getChartsFromFile();

    const authStatus = await fetchAuthStatus(fetcher, options);

    if (!authStatus.isLoggedIn) {
        return {
            source: "file",
            isLoggedIn: false,
            profile: {
                ...fileProfile,
                username: authStatus.username || fileProfile.username,
            },
            charts: fileCharts,
            authMessage: authStatus.message,
        };
    }

    try {
        const apiData = await fetchDashboardFromApi(fetcher, options);
        if (!apiData) {
            return {
                source: "file",
                isLoggedIn: true,
                profile: {
                    ...fileProfile,
                    username: authStatus.username || fileProfile.username,
                },
                charts: fileCharts,
                error: "用户数据接口未配置或与桥接地址冲突，已回退本地数据",
                authMessage: authStatus.message,
            };
        }

        return {
            source: "api",
            isLoggedIn: true,
            profile: {
                ...apiData.profile,
                username: apiData.profile.username || authStatus.username,
            },
            charts: apiData.charts,
            authMessage: authStatus.message,
        };
    } catch (error) {
        return {
            source: "file",
            isLoggedIn: true,
            profile: {
                ...fileProfile,
                username: authStatus.username || fileProfile.username,
            },
            charts: fileCharts,
            error: `读取用户 API 失败，已回退 file 数据：${error instanceof Error ? error.message : String(error)
                }`,
            authMessage: authStatus.message,
        };
    }
}

export async function resolveUserProfile(
    fetcher: typeof fetch = fetch,
    options: ResolveUserDataOptions = {},
): Promise<UserProfileResolveResult> {
    const dashboard = await resolveUserDashboardData(fetcher, options);
    return {
        source: dashboard.source,
        isLoggedIn: dashboard.isLoggedIn,
        profile: dashboard.profile,
        error: dashboard.error,
        authMessage: dashboard.authMessage,
    };
}

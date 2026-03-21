// Place any global data in this file.
// You can import this data from anywhere in your site by using the `import` keyword.

// ===== 站点基础配置 =====
export type SiteConfig = {
    title: string;
    description: string;
    themeColor: string;
    defaultLanguage: string;
    image: {
        adaptive: boolean; // 是否启用图片自适应显示
    };
    favicon?: string;
};

export const siteConfig: SiteConfig = {
    title: '灵·诊',
    description: 'Welcome to my website!',
    defaultLanguage: 'zh-CN',
    image: {
        adaptive: false, // 开关：是否启用响应式图片（srcset/sizes），以减少不同设备上的传输负载和提升性能
    },
    themeColor: 'rgb(35, 138, 255)',
    favicon: '/public/icon.png', // 可选：站点的favicon路径（public 目录下资源用绝对路径）
};

// ===== 侧边滚动条配置 =====
export type ScrollbarConfig = {
    size: `${number}px`;
    color: string;
};

export function getScrollbarConfig(): ScrollbarConfig {
    return {
        size: '1px',
        color: 'rgb(var(--gray-light))',
    };
}

// ===== Markdown 渲染配置 =====
export type MarkdownRenderConfig = {
    desktopContentWidth: `${number}%`;
    fontScale: `${number}%`;
};

export function getMarkdownRenderConfig(): MarkdownRenderConfig {
    return {
        desktopContentWidth: '75%',
        fontScale: '75%',
    };
}

export type IconifyFa6Icon =
    | `fa6-brands:${string}`
    | `fa6-solid:${string}`
    | `fa6-regular:${string}`;

// ===== 页脚图标以及链接 =====
export type FooterSocialLink = {
    name: string;
    href: string;
    icon: IconifyFa6Icon;
};

export const FOOTER_SOCIAL_LINKS: FooterSocialLink[] = [
    {
        name: 'GitHub',
        href: 'https://github.com/wanshushan',
        icon: 'fa6-brands:github',
    },
    {
        name: 'QQ',
        href: 'https://qq.com',
        icon: 'fa6-brands:qq',
    },
    {
        name: 'B站',
        href: 'https://bilibili.com',
        icon: 'fa6-brands:bilibili',
    },
];

// ===== 导航菜单配置 =====
/**
 * 导航菜单项的顺序枚举
 * 通过修改此枚举的值来控制菜单项的显示顺序
 */
export enum NavigationItemOrder {
    HOME = 0,
    BLOG = 1,
    PROJECT = 2,
    ABOUT = 3,
}

/**
 * 导航菜单项
 */
export type NavigationItem = {
    order: NavigationItemOrder;
    href: string;
    label: string;
    icon?: IconifyFa6Icon; // 可选的 Iconify 图标标识
};

export const NAVIGATION_ITEMS: NavigationItem[] = [
    {
        order: NavigationItemOrder.HOME,
        href: '/',
        label: '主页',
        icon: 'fa6-regular:bookmark',
    },
    {
        order: NavigationItemOrder.BLOG,
        href: '/blog',
        label: '资料',
        icon: 'fa6-regular:newspaper',
    },
    {
        order: NavigationItemOrder.PROJECT,
        href: '/project',
        label: '问诊',
        icon: 'fa6-regular:message',
    },
    {
        order: NavigationItemOrder.ABOUT,
        href: '/about',
        label: '关于',
        icon: 'fa6-regular:circle-question',
    },
];

/**
 * 获取排序后的导航菜单项
 */
export function getNavigationItems(): NavigationItem[] {
    return NAVIGATION_ITEMS.sort((a, b) => a.order - b.order);
}

// ===== 顶部社交链接配置 =====
/**
 * 顶部右侧社交链接（如 GitHub）
 * 与 FOOTER_SOCIAL_LINKS 区分，此处为顶部栏显示的链接
 */
export type SocialLink = {
    name: string;
    href: string;
    icon?: IconifyFa6Icon; // 可选的 Iconify 图标标识
    external?: boolean;
};

function normalizePublicEnvValue(value: unknown): string {
    return typeof value === "string" ? value.trim() : "";
}

export const AUTH_STATE_STORAGE_KEY =
    normalizePublicEnvValue(import.meta.env.PUBLIC_AUTH_STATE_STORAGE_KEY) ||
    "LINGZHEN_AUTH_LOGGED_IN";

export const AUTH_USERNAME_STORAGE_KEY =
    normalizePublicEnvValue(import.meta.env.PUBLIC_AUTH_USERNAME_STORAGE_KEY) ||
    "LINGZHEN_AUTH_USERNAME";

export const AUTH_DEFAULT_LOGGED_IN =
    normalizePublicEnvValue(import.meta.env.PUBLIC_AUTH_DEFAULT_LOGGED_IN).toLowerCase() ===
    "true";

export function getAuthStateStorageKey(): string {
    return AUTH_STATE_STORAGE_KEY;
}

export function getAuthUsernameStorageKey(): string {
    return AUTH_USERNAME_STORAGE_KEY;
}

// ===== 用户资料配置（登录后走 API，未登录走本地） =====

export type UserProfileLink = {
    name: string;
    href: string;
    icon?: IconifyFa6Icon;
};

export type UserProfile = {
    username?: string;
    bio?: string;
    avatar?: string;
    links: UserProfileLink[];
};

export type UserChartPoint = {
    x: number;
    y: number;
};

export type UserChartDefinition = {
    id: string;
    title: string;
    xAxisName: string;
    yAxisName: string;
    fallbackPoints: UserChartPoint[];
};

export const USER_CHART_DEFINITIONS: UserChartDefinition[] = [
    {
        id: "chart-1",
        title: "趋势图 1",
        xAxisName: "时间",
        yAxisName: "指标A",
        fallbackPoints: [
            { x: 1, y: 10 },
            { x: 2, y: 10 },
            { x: 3, y: 10 },
            { x: 4, y: 10 },
            { x: 5, y: 10 },
            { x: 6, y: 10 },
        ],
    },
    {
        id: "chart-2",
        title: "趋势图 2",
        xAxisName: "时间",
        yAxisName: "指标B",
        fallbackPoints: [
            { x: 1, y: 10 },
            { x: 2, y: 10 },
            { x: 3, y: 10 },
            { x: 4, y: 10 },
            { x: 5, y: 10 },
            { x: 6, y: 10 },
        ],
    },
    {
        id: "chart-3",
        title: "趋势图 3",
        xAxisName: "时间",
        yAxisName: "指标C",
        fallbackPoints: [
            { x: 1, y: 10 },
            { x: 2, y: 10 },
            { x: 3, y: 10 },
            { x: 4, y: 10 },
            { x: 5, y: 10 },
            { x: 6, y: 10 },
        ],
    },
    {
        id: "chart-4",
        title: "趋势图 4",
        xAxisName: "时间",
        yAxisName: "指标D",
        fallbackPoints: [
            { x: 1, y: 10 },
            { x: 2, y: 10 },
            { x: 3, y: 10 },
            { x: 4, y: 10 },
            { x: 5, y: 10 },
            { x: 6, y: 10 },
        ],
    },
];

export type UserApiSourceConfig = {
    endpoint: string;
    timeoutMs: number;
    mapping: {
        usernameField: string;
        bioField: string;
        avatarField: string;
        linksField: string;
        chartsField: string;
        chartIdField: string;
        chartPointsField: string;
        pointXField: string;
        pointYField: string;
    };
};

export type UserAuthApiConfig = {
    statusEndpoint: string;
    loginEndpoint: string;
    registerEndpoint: string;
    logoutEndpoint: string;
    timeoutMs: number;
    mapping: {
        loggedInField: string;
        usernameField: string;
        messageField: string;
    };
};

export type UserProfileDataConfig = {
    fallbackUsername: string;
    userPagePath: string;
    authPagePath: string;
    bridgeEndpoint: string;
    file: UserProfile;
    api: UserApiSourceConfig;
    auth: UserAuthApiConfig;
};

export const USER_PROFILE_CONFIG: UserProfileDataConfig = {
    fallbackUsername: "User",
    userPagePath: "/user",
    authPagePath: "/auth",
    bridgeEndpoint: "/user/api.json",
    file: {
        username: "User",
        bio: "你尚未登录，请登录使用",
        avatar: "",
        links: FOOTER_SOCIAL_LINKS.map((item) => ({
            name: item.name,
            href: item.href,
            icon: item.icon,
        })),
    },
    api: {
        endpoint: "/api/user/profile",
        timeoutMs: 5000,
        mapping: {
            usernameField: "username",
            bioField: "bio",
            avatarField: "avatar",
            linksField: "links",
            chartsField: "charts",
            chartIdField: "id",
            chartPointsField: "points",
            pointXField: "x",
            pointYField: "y",
        },
    },
    auth: {
        statusEndpoint: "/api/auth/status",
        loginEndpoint: "/api/auth/login",
        registerEndpoint: "/api/auth/register",
        logoutEndpoint: "/api/auth/logout",
        timeoutMs: 5000,
        mapping: {
            loggedInField: "loggedIn",
            usernameField: "username",
            messageField: "message",
        },
    },
};

function normalizeNonEmptyString(value?: string): string {
    return (value || "").trim();
}

export function getUserFallbackName(): string {
    return normalizeNonEmptyString(USER_PROFILE_CONFIG.fallbackUsername) || "User";
}

export function getConfiguredUsername(): string {
    return normalizeNonEmptyString(USER_PROFILE_CONFIG.file.username) || getUserFallbackName();
}

export function getUserBridgeEndpoint(): string {
    return normalizeNonEmptyString(USER_PROFILE_CONFIG.bridgeEndpoint) || "/user/api.json";
}

export function getUserPagePath(): string {
    return normalizeNonEmptyString(USER_PROFILE_CONFIG.userPagePath) || "/user";
}

export function getAuthPagePath(): string {
    return normalizeNonEmptyString(USER_PROFILE_CONFIG.authPagePath) || "/auth";
}

export const HEADER_SOCIAL_LINKS: SocialLink[] = [
    {
        name: getConfiguredUsername(),
        href: getUserPagePath(),
        icon: 'fa6-regular:address-card',
        external: false,
    },
];

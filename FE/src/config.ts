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
        label: '项目',
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
};

export const HEADER_SOCIAL_LINKS: SocialLink[] = [
    {
        name: 'GitHub',
        href: 'https://github.com/wanshushan',
        icon: 'fa6-regular:address-card',
    },
];

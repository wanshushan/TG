// Place any global data in this file.
// You can import this data from anywhere in your site by using the `import` keyword.

export const SITE_TITLE = '灵·舌';
export const SITE_DESCRIPTION = 'Welcome to my website!';


//  TODO: 目前这些常量分散在各个文件中，考虑集中管理。


// 页脚图标以及链接

export type FooterSocialLink = {
    name: string;
    href: string;
    icon: `fa6-brands:${string}`;
};

export const FOOTER_SOCIAL_LINKS: FooterSocialLink[] = [
    {
        name: "GitHub",
        href: "https://github.com/wanshushan",
        icon: "fa6-brands:github"
    },
    {
        name: "QQ",
        href: "https://qq.com",
        icon: "fa6-brands:qq"
    },
    {
        name: "B站",
        href: "https://bilibili.com",
        icon: "fa6-brands:bilibili"
    }
];
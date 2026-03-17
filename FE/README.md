## 关于项目前端架构

- 使用Astro框架构建
- 大部分配置可以在`src/config.ts`中进行调整
- 内容主要放在`src/content`目录下，使用md或mdx格式

## 前端文件结构：

```text
FE/
├── public
│   ├── fonts
│   │   ├── atkinson-bold.woff
│   │   └── atkinson-regular.woff
│   ├── favicon.ico
│   └── favicon.svg
├── src
│   ├── assets
│   │   ├── blog-placeholder-1.jpg
│   │   ├── blog-placeholder-2.jpg
│   │   ├── blog-placeholder-3.jpg
│   │   ├── blog-placeholder-4.jpg
│   │   ├── blog-placeholder-5.jpg
│   │   └── blog-placeholder-about.jpg
│   ├── components
│   │   ├── BaseHead.astro
│   │   ├── Footer.astro
│   │   ├── FormattedDate.astro
│   │   ├── Header.astro
│   │   └── HeaderLink.astro
│   ├── content
│   │   ├── about
│   │   │   └── about.md
│   │   ├── blog
│   │   │   ├── test
│   │   │   │   ├── pjs2.png
│   │   │   │   ├── pjshare1.png
│   │   │   │   └── test.md
│   │   │   ├── markdown-style-guide.md
│   │   │   └── using-mdx.mdx
│   │   └── index
│   │       └── index.mdx
│   ├── layouts
│   │   └── BlogPost.astro
│   ├── lib
│   │   ├── SCROLLBAR_IMPLEMENTATION.md
│   │   └── SCROLLBAR_USAGE_GUIDE.md
│   ├── pages
│   │   ├── blog
│   │   │   ├── [...slug].astro
│   │   │   └── index.astro
│   │   ├── project
│   │   │   ├── chat
│   │   │   │   ├── 26-03-17T18-08.md
│   │   │   │   └── 26-03-17T21-15.md
│   │   │   ├── api.json
│   │   │   ├── api.json.ts
│   │   │   ├── chat.ts
│   │   │   └── index.astro
│   │   ├── about.astro
│   │   ├── index.astro
│   │   └── rss.xml.js
│   ├── styles
│   │   └── global.css
│   ├── types
│   │   └── iconify-json.d.ts
│   ├── config.ts
│   └── content.config.ts
├── .env
├── .gitignore
├── astro.config.mjs
├── package-lock.json
├── package.json
├── pnpm-lock.yaml
├── README.md
└── tsconfig.json
```



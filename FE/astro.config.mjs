// @ts-check

import mdx from '@astrojs/mdx';
import node from '@astrojs/node';
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';

import react from '@astrojs/react';

// https://astro.build/config
export default defineConfig({
    site: 'https://tg.wanshushan.top/',
    output: 'server',
    adapter: node({ mode: 'standalone' }),
    security: {
        checkOrigin: false,
    },
    integrations: [mdx(), sitemap(), react()],
    vite: {
        resolve: {
            alias: {
                '@': fileURLToPath(new URL('./src', import.meta.url)),
            },
        },
        server: {
            allowedHosts: ['tg.wanshushan.top']  // 替换为你的域名
        }
    }
});
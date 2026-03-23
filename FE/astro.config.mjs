// @ts-check

import mdx from '@astrojs/mdx';
import node from '@astrojs/node';
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
	site: 'https://tg.wanshushan.top/',
	output: 'server',
	adapter: node({ mode: 'standalone' }),
	security: {
		checkOrigin: false,
	},
	integrations: [mdx(), sitemap()],
	vite: {
		server: {
			allowedHosts: ['tg.wanshushan.top']  // 替换为你的域名
		}
	}
});



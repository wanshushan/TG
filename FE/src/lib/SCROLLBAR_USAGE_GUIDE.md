/**
 * OverlayScrollbars 滚动条样式使用指南
 * 
 * 该文档展示如何在 Astro 项目中复用和扩展滚动条主题
 */

// ===== 示例 1: 在某个容器上启用横向滚动条 =====
// 在 Astro 组件中使用 data 属性标记需要横向滚动的容器：

/*
<div data-horizontal-scroll="true" class="code-block">
  <pre><code>// 长代码行在这里...</code></pre>
</div>

<style>
  .code-block {
    overflow-x: auto;
    max-width: 100%;
  }
</style>

脚本：
import { initializeHorizontalScrollbars } from '../lib/scrollbar';

// 在需要时手动初始化特定容器
document.addEventListener('DOMContentLoaded', () => {
  initializeHorizontalScrollbars();
});
*/

// ===== 示例 2: 为特定容器创建自定义滚动条配置 =====

/*
// 在 src/lib/scrollbar.ts 中添加新的配置函数：

export const customScrollConfig: Options = {
  autoHide: 'never',  // 始终显示，不自动隐藏
  scrollbars: {
    theme: 'os-theme-custom',
  },
};

// 在组件中使用：
import { OverlayScrollbars } from 'overlayscrollbars';
import { customScrollConfig } from '../lib/scrollbar';

export function initializeCustomScrollbar(element: HTMLElement) {
  OverlayScrollbars(element, customScrollConfig);
}
*/

// ===== 示例 3: 与框架组件集成 =====

/*
// 如果使用了 React 或其他框架组件，可以在 useEffect 中初始化：

import { useEffect } from 'react';
import { OverlayScrollbars } from 'overlayscrollbars';

export function ScrollableContainer() {
  const containerRef = useRef(null);

  useEffect(() => {
    if (containerRef.current) {
      OverlayScrollbars(containerRef.current, {
        autoHide: 'move',
        autoHideDelay: 500,
        scrollbars: {
          theme: 'os-theme-custom',
        },
      });
    }
  }, []);

  return (
    <div ref={containerRef} style={{ maxHeight: '500px', overflow: 'auto' }}>
      {/* 内容 */}
    </div>
  );
}
*/

// ===== 示例 4: 根据系统主题动态调整颜色 =====

/*
// 已在 src/lib/scrollbar.ts 中实现的 updateScrollbarTheme() 函数
// 会根据系统深色模式自动调整：
// - light mode: 黑色 0.4/0.5/0.6 透明度
// - dark mode: 白色 0.4/0.5/0.6 透明度

// 如需手动调用更新：
import { updateScrollbarTheme } from '../lib/scrollbar';

// 手动更新主题
updateScrollbarTheme();

// 或监听变化：
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  updateScrollbarTheme();
});
*/

// ===== 示例 5: 自定义 CSS 变量覆盖滚动条样式 =====

/*
// 在你的 CSS 中可以覆盖主题变量：

:root {
  /* 覆盖默认颜色 */
  --scrollbar-normal: rgba(100, 100, 100, 0.3);
  --scrollbar-hover: rgba(100, 100, 100, 0.5);
  --scrollbar-active: rgba(100, 100, 100, 0.8);
}

/* 为特定页面或模式应用不同的样式 */
@media (prefers-color-scheme: dark) {
  :root {
    --scrollbar-normal: rgba(200, 200, 200, 0.3);
    --scrollbar-hover: rgba(200, 200, 200, 0.5);
    --scrollbar-active: rgba(200, 200, 200, 0.8);
  }
}
*/

// ===== CSS 变量汇总 =====
/*
:root {
  /* 滚动条颜色（按亮度） */
  --scrollbar-normal: rgba(0, 0, 0, 0.4);      /* 默认状态 */
  --scrollbar-hover: rgba(0, 0, 0, 0.5);       /* 悬停时 */
  --scrollbar-active: rgba(0, 0, 0, 0.6);      /* 活跃/拖拽时 */
}
*/

// ===== 主题类名 =====
/*
所有滚动条容器默认使用类名: .os-theme-custom

如需创建新主题，在 CSS 中定义，例如：
.os-theme-light { ... }
.os-theme-dark { ... }

然后在初始化时指定：
scrollbars: {
  theme: 'os-theme-light',  // 替换为你的主题类名
}
*/

export default "这是一个纯文档文件，展示滚动条使用方式";
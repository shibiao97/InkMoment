# 🔍 片刻 — 全面审查报告

> 审查日期：2026-05-22
> 范围：Bug / 性能 / 动效交互 / 模型算法降级方案

---

## 目录

- [一、严重 Bug（P0）](#一严重-bugp0)
- [二、中等 Bug（P1）](#二中等-bugp1)
- [三、性能优化建议](#三性能优化建议)
- [四、动效与交互优化](#四动效与交互优化)
- [五、模型/算法降级方案完整清单](#五模型算法降级方案完整清单)
- [六、优先级排序](#六优先级排序)

---

## 一、严重 Bug（P0）

### Bug 1：`renderRecent()` 引用不存在的 DOM 元素，导致应用启动崩溃

- **文件**：`static/app.js:231`
- **严重程度**：🔴 高

```javascript
const wrap = $("recent-folders");  // HTML 中不存在 id="recent-folders"
wrap.innerHTML = "";               // TypeError: Cannot set property 'innerHTML' of null
```

HTML 中没有 `id="recent-folders"` 的元素，`$()` 返回 `null`，后续操作直接抛异常。此函数在 `bootstrap()` 中调用且不在 try-catch 内，**整个应用无法初始化**。

**修复**：在 `renderRecent` 开头加 `if (!wrap) return;`，或在 index.html 中补上 `<div id="recent-folders" class="recent-folders"></div>`。

---

### Bug 2：`item.name` 在 innerHTML 中未转义，存在 XSS 风险

- **文件**：`static/app.js:1203`、`static/app.js:2264`、`static/app.js:2299`
- **严重程度**：🔴 高

```javascript
card.innerHTML = `<img ... alt="${item.name}">`;  // item.name 未转义
```

如果文件名含双引号（如 `photo"test.jpg`），可以闭合 `alt` 属性注入 HTML。代码中已有 `escapeHtml()` 工具函数（`app.js:915`），在终端行渲染中正确使用，但上述三处遗漏。

**修复**：将 `alt="${item.name}"` 改为 `alt="${escapeHtml(item.name)}"`。

---

### Bug 3：grouper.py 能力级异常检测可能遗漏

- **文件**：`grouper.py:658-668`
- **严重程度**：🔴 高

```python
try:
    import llm_judge
    _capability_excs += (llm_judge.LLMJudgeError,)
except Exception:
    pass  # 静默跳过！

try:
    import vision as _vision_mod
    _capability_excs += (_vision_mod.VisionUnavailable,)
except Exception:
    pass  # 静默跳过！
```

如果 `llm_judge` 或 `vision` 模块导入失败（而非未安装），`_capability_excs` 元组不完整。后续 `LLMJudgeError` / `VisionUnavailable` 不会被识别为致命异常，而是被当成图级异常静默跳过——**500 张图可能全部悄悄 skip**。

**修复**：至少打 warning 日志；或在 `_require_engine` 校验通过后，延迟到 worker 内部再 import。

---

## 二、中等 Bug（P1）

### Bug 4：`loadCurrent()` 缺少错误处理，UI 可能卡死

- **文件**：`static/app.js:1966-1972`

```javascript
async function loadCurrent() {
  const r = await fetchJSON("/api/group");   // 失败则异常向上抛
  const s = await fetchJSON("/api/status");  // 同上
  ...
}
```

调用方 `enterArena()` 也没有 catch。网络波动时 UI 停留在空白/旧状态，用户无法操作。

**修复**：加 try-catch，失败时显示 toast 提示并允许重试。

---

### Bug 5：`llm_judge._CLIENT` / `_MODELS_CACHE` 直接修改，绕过锁

- **文件**：`app.py:2062-2063`、`app.py:1950`

```python
llm_judge._CLIENT = None
llm_judge._MODELS_CACHE = {"at": 0.0, "data": None}
```

直接修改 llm_judge 模块全局变量，绕过了 `_CLIENT_LOCK`，与 `_client()` 函数中的锁保护逻辑冲突，可能导致竞态条件。

**修复**：通过 llm_judge 暴露的 `reset_client()` 之类的方法来操作，或在 `_CLIENT_LOCK` 保护下修改。

---

### Bug 6：`confirmDialog` 可叠加导致双重回调

- **文件**：`static/app.js:161-177`

如果在一个 `confirmDialog` 未关闭时又调用另一个，两个 Promise 的监听器会叠加在同一个按钮上，用户点一次"确定"触发两个 resolve。

**修复**：在添加新监听器前先移除所有旧监听器，或使用一次性标记。

---

### Bug 7：HEIF 注册失败完全静默

- **文件**：`app.py:43-47`、`grouper.py:22-26`

```python
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass  # 用户不知道 HEIC 文件无法打开
```

**修复**：至少 `logger.info("pillow_heif 不可用，HEIC/HEIF 支持已跳过")`。

---

### Bug 8：`load_state` 失败仅打日志，用户不知情

- **文件**：`app.py:487-514`

Session 丢失后用户看到空界面，不知道之前的进度已丢失。

**修复**：向前端返回明确的错误状态，让 UI 展示提示。

---

### Bug 9：持锁期间做磁盘 I/O

- **文件**：`app.py:2454-2456`

`_finalize_group_locked()` 内调用 `save_state(SESSION)` 两次，涉及 JSON 序列化 + 文件写入，在持锁期间做 I/O 会阻塞其他等待 LOCK 的线程。

**修复**：先复制需要保存的数据，释放锁后再做 I/O；或改为只 save 一次。

---

### Bug 10：quality.py saliency 运行时静默降级

- **文件**：`quality.py:414-454`

虽然启动期有校验，但运行时 saliency 计算异常仍静默返回 None，无日志。`salient_sharpness` 信号丢失后，模糊判定可能误判。

**修复**：运行时 saliency 计算失败时打 warning 日志。

---

### Bug 11：`_safe_open_image` 吞掉所有异常

- **文件**：`app.py:1260-1269`

无法区分"文件损坏"、"权限错误"、"格式不支持"等不同情况，全部返回 None。

**修复**：区分异常类型，至少对权限错误打 warning。

---

### Bug 12：`api_skipped` 读取 SESSION 时未获取 LOCK

- **文件**：`app.py:2924-2939`

部分路由读取全局 SESSION 时未获取 LOCK，与后台线程的写入可能产生竞态。

---

## 三、性能优化建议

### 优化 1：缩放拖拽 `mousemove` 未用 rAF 节流 🔴

- **文件**：`static/app.js:2182-2188`

```javascript
window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  zoom.tx = ...; zoom.ty = ...;
  clampPan();
  applyZoom();  // 每次 mousemove 都修改 DOM
});
```

**修复**：用 `requestAnimationFrame` 包裹 `applyZoom()`，避免一帧内多次重绘。

---

### 优化 2：滚轮缩放未节流 🔴

- **文件**：`static/app.js:2160-2169`

快速滚动时 wheel 事件频率极高，每次都修改 DOM。

**修复**：同样用 rAF 节流，或合并连续 wheel 事件。

---

### 优化 3：`pushTerminalLine` 每行强制同步布局 🟠

- **文件**：`static/app.js:945`

```javascript
const lineH = row.getBoundingClientRect().height || (12 * 1.55);
```

每添加一行终端日志都强制同步布局。快速扫描时（每秒多行）造成布局抖动。

**修复**：缓存行高值，仅在字体/容器变化时重新计算。

---

### 优化 4：`startCollectingAnimation` 循环中 getBoundingClientRect 🟠

- **文件**：`static/app.js:864-876`

在循环中对每个元素调用 `getBoundingClientRect()`，读写交替触发多次布局重排。

**修复**：先批量读取所有 rect，再批量写入样式。

---

### 优化 5：照片墙/胜者相册全量重建 DOM 🟡

- **文件**：`static/app.js:1184-1230`、`static/app.js:2274-2337`

每次调用都 `innerHTML = ""` 然后重建所有卡片。大量照片时造成明显卡顿。

**修复**：使用增量更新（diff），或对大量图片使用虚拟列表。

---

### 优化 6：CSS 死代码约 200+ 行 🟢

| 文件:行号 | 类名 | 说明 |
|-----------|------|------|
| `style.css:380-391` | `.processing-shell` | HTML 用的是 `.proc-shell` |
| `style.css:392-399` | `.proc-title` | HTML 用的是 `.proc-title-sm` |
| `style.css:968-1041` | `.winner-card` 及相关 | JS 用的是 `.album-cell` |
| `style.css:2846-2985` | `.proc-stream` 约 140 行 | 注释标注"HTML 已弃用" |
| `style.css:810-808` | `.hints` / `.shortcut-list` 等 | HTML 和 JS 均无引用 |
| `style.css:874-880` | `.done-stats` | HTML 用的是 `.done-stats-hidden` |

**修复**：删除未使用的 CSS，减少文件体积和解析时间。

---

### 优化 7：`.exif-line span.exif-diff` 重复定义 🟢

- **文件**：`style.css:1679-1682` 和 `style.css:2300-2303`

第二次覆盖第一次（颜色从 clay 红改成 gold），应删除第一次定义。

---

### 优化 8：`:root` 块出现了三次 🟢

- **文件**：`style.css:10-50`、`style.css:1917-1923`、`style.css:2430-2437`

分散定义增加维护难度，建议合并。

---

### 优化 9：`--ink-soft` CSS 变量从未定义 🟢

- **文件**：`style.css:1696`

```css
.llm-comment {
  color: var(--ink-soft, #555);  /* --ink-soft 未在 :root 中定义 */
}
```

始终使用 fallback 值 `#555`。应将其加入 `:root` 或直接使用硬编码值。

---

## 四、动效与交互优化

### 动效 1：判决动画时长不匹配 🔴

- **文件**：`static/app.js:9` vs `static/style.css:743-748`

| 维度 | JS | CSS |
|------|----|-----|
| 等待时间 | `VERDICT_HOLD_MS = 380ms` | — |
| 动画时长 | — | `animation: pop .55s` (550ms) |

JS 等待 380ms 后就开始切换，CSS 动画还剩 170ms 被截断，判决徽章弹出动画不完整。

**修复**：`VERDICT_HOLD_MS` 改为至少 550ms。

---

### 动效 2：视图切换无退出动画 🟠

- **文件**：`static/style.css:87-92`

旧视图直接 `display: none`，没有淡出/滑出过渡，视觉突兀。

**修复**：添加退出动画类，用 `animationend` 事件后再隐藏。

---

### 动效 3：Lightbox 打开无预加载，可能闪白 🟠

- **文件**：`static/app.js:2474-2479`

```javascript
$("lb-img").src = imgUrl(item.path);  // 直接设置，无预加载
```

如果原图较大，lightbox 打开后会短暂显示空白再出现图片。

**修复**：先显示 loading 状态，图片 onload 后再显示。

---

### 动效 4：照片墙替换单元格时可能出现空白间隙 🟡

- **文件**：`static/app.js:784-791`

旧图淡出后 220ms 延迟才开始加载新图，如果新图加载也慢，单元格可能空白。

**修复**：先加载新图，onload 后再淡出旧图。

---

### 动效 5：indeterminate 进度条动画末尾闪烁 🟡

- **文件**：`static/style.css:433-436`

```css
@keyframes indeterminate {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(330%); }
}
```

`330%` 在动画末尾可能让进度条短暂出现在容器右边缘外。

**修复**：改为 `400%` 或更高确保完全移出视野。

---

### 动效 6：`.img-frame` 过渡属性过多 🟡

- **文件**：`static/style.css:616-621`

同时过渡 5 个属性（border-color, box-shadow, transform, filter, opacity），其中 `filter` 和 `transform` 的组合在低端设备上可能导致卡顿。

**修复**：考虑将 `filter` 过渡单独处理，或使用 `will-change: transform, filter` 提示浏览器优化。

---

### 交互 1：`clearArkKey` 使用原生 `confirm()` 风格不一致 🟡

- **文件**：`static/app.js:376`

应用其他地方都使用自定义 `confirmDialog()`，此处却用了浏览器原生 `confirm()`。

**修复**：改用 `confirmDialog()`。

---

### 交互 2：确认弹窗不支持 Escape 键关闭 🟡

- **文件**：`static/app.js:161-177`

用户只能用鼠标点"取消"按钮。

**修复**：添加 `keydown` 监听，Escape 键触发 cancel。

---

### 交互 3：`engine-opt` 点击导致 `syncEngineSwitch` 被调用两次 🟢

- **文件**：`static/app.js:285-297`

点击标签时，click 处理器手动调用一次，radio change 事件又触发一次。无害但浪费。

**修复**：在 click handler 中调用 `e.preventDefault()` 或去掉手动调用。

---

### 交互 4：`#proc-terminal` 可点击展开但无键盘支持 🟢

- **文件**：`static/app.js:896-907`

缺少 `tabindex`、`role="button"` 或键盘事件处理。

---

### 交互 5：多个 `<main>` 元素违反 HTML 规范 🟢

- **文件**：`static/index.html:38`、`308`、`362`、`433`

HTML 规范要求每个文档最多一个 `<main>` 元素。当前有 4 个。

**修复**：只保留一个 `<main>`，其他改为 `<div role="region">`。

---

### 交互 6：缩略图/Strip/Lightbox 图片缺少 alt 文本 🟢

- **文件**：`static/app.js:1854`、`555-558`、`1566`、`static/index.html:632`

多处图片 `alt=""`，屏幕阅读器无法识别其用途。

---

### 交互 7：Toast (z-index: 200) 覆盖在 Modal (z-index: 150) 之上 🟢

- **文件**：`static/style.css:1869`、`1885`

Toast 出现在 Modal 之上可能遮挡重要操作按钮。需确认是否符合设计意图。

---

## 五、模型/算法降级方案完整清单

### A. 真正的静默降级（仅 1 处）

| # | 位置 | 降级内容 | 影响 |
|---|------|----------|------|
| 1 | `app.py:43-47`、`grouper.py:22-26` | `pillow_heif` 未安装 → HEIF/HEIC 支持静默跳过 | 用户不知道 HEIC 文件无法打开 |

---

### B. 信号缺失（非能力降级，但影响判定精度）

| # | 位置 | 缺失信号 | 后果 |
|---|------|----------|------|
| 2 | `quality.py:414-454` | cv2 saliency 创建/计算失败 → `salient_sharpness=None` | 模糊判定可能误判（无人脸时无法用显著性锐度救回），静默丢失信号无日志 |
| 3 | `fast_quality.py:402-428` | 同上，fast 模式 saliency 失败 | 同上 |
| 4 | `fast_quality.py:305-312` | saliency_map 为 None → 构图分退化到固定 0.5 | 构图评估失去区分度（设计性退化） |
| 5 | `quality.py:576-583` | 单张图 `eye_score` 计算失败 → `None` | 闭眼检测信号丢失（打了 warning 但仍为 None） |
| 6 | `quality.py:273-275` | 无人脸时用显著性锐度替代 | 模糊判定可能不够精确（设计性替代） |
| 7 | `grouper.py:142-143` | EXIF 日期读取失败 → `None` | 时间信号丢失，影响连拍检测（无日志） |
| 8 | `app.py:3041-3045` | 探测人脸支持失败 → `face=False` | 人脸感知功能被关闭（静默降级） |

---

### C. 权重重分配（信号缺失时的自适应）

| # | 位置 | 缺失信号 | 权重转移 | 影响 |
|---|------|----------|----------|------|
| 9 | `clustering.py:376-382` | 两张图都无人脸 | face → dino 40%, time 30%, exif 30% | 分组仍可进行，精度略降 |
| 10 | `clustering.py:370-373` | GPS 缺失 | gps → exif | EXIF 权重增大 |
| 11 | `fast_clustering.py:343-368` | 颜色直方图缺失 | color → hash | hash 权重增大 |
| 12 | `fast_clustering.py:343-368` | GPS 缺失 | gps → exif | 同 #10 |

---

### D. 算法级降级

| # | 位置 | 降级内容 | 影响 |
|---|------|----------|------|
| 13 | `fast_clustering.py:405-407` | ORB 几何验证内点 < 5 且 hash > 0.55 → 判定为 hash 误报，相似度降级到 0.55 | 防止 hash 碰撞导致的误分组 |

---

### E. 显示层降级

| # | 位置 | 降级内容 | 影响 |
|---|------|----------|------|
| 14 | `app.py:2580-2582` | 图片解码失败 → 返回 SVG 占位图 | 用户看到占位图而非报错 |
| 15 | `app.py:1260-1269` | `_safe_open_image` 失败 → 返回 None | 调用方跳过该图 |

---

### F. 安装期 Fallback

| # | 位置 | 降级内容 | 影响 |
|---|------|----------|------|
| 16 | `scripts/launcher.py:335` | 国内镜像为主，PyPI 官方为 fallback | 镜像缺包时自动回退到官方源 |

---

### G. 不降级（硬失败）的关键路径

| # | 位置 | 失败行为 | 说明 |
|---|------|----------|------|
| 17 | `vision.py:75-81` | DINOv2 依赖缺失 → 抛 `VisionUnavailable` | 任务终止 |
| 18 | `vision.py:116-123` | NIMA 依赖缺失 → 抛 `VisionUnavailable` | 任务终止 |
| 19 | `vision.py:189-195` | MUSIQ 依赖缺失 → 抛 `VisionUnavailable` | 任务终止 |
| 20 | `vision.py:221-227` | CLIP-IQA+ 依赖缺失 → 抛 `VisionUnavailable` | 任务终止 |
| 21 | `vision.py:257-262` | InsightFace 依赖缺失 → 抛 `VisionUnavailable` | 任务终止 |
| 22 | `llm_judge.py:394-489` | LLM 调用重试 4 次仍失败 → 抛 `LLMJudgeError` | 任务终止 |
| 23 | `app.py:1694-1754` | `_require_engine` 启动期校验，缺一即抛 | 任务无法启动 |
| 24 | `grouper.py:756` | 分组分发器失败直接抛 | 不再静默回退 |

---

### H. 已修复的旧版静默降级

| # | 旧代码 | 修复标记 | 修复后行为 |
|---|--------|----------|------------|
| 25 | `except Exception: return {}` 吞掉 InsightFace 崩溃 | A2 | 向上抛异常 |
| 26 | `try: import vision except: vision = None` 兜底 | A3 | 直接 import，失败向上抛 |
| 27 | `eye_score` 异常被静默吞成 None | A4 | 至少打 warning |
| 28 | expert 模式 saliency 用 cv2.saliency 但启动期不校验 | A5 | 启动期校验 cv2 contrib |
| 29 | 能力级异常和图级异常不区分 | A6 | `_is_fatal_capability` 区分 |

---

## 六、优先级排序

| 优先级 | 项目 | 类型 |
|--------|------|------|
| 🔴 P0 | Bug 1: renderRecent 崩溃 | Bug |
| 🔴 P0 | Bug 2: innerHTML XSS | Bug |
| 🔴 P0 | Bug 3: 能力级异常检测遗漏 | Bug |
| 🟠 P1 | Bug 4: loadCurrent 无错误处理 | Bug |
| 🟠 P1 | Bug 5: llm_judge 全局变量无锁 | Bug |
| 🟠 P1 | 动效 1: 判决动画时长不匹配 | 动效 |
| 🟠 P1 | 优化 1-2: mousemove/wheel 未节流 | 性能 |
| 🟡 P2 | Bug 6-12: 中等 Bug | Bug |
| 🟡 P2 | 动效 2-6: 退出动画/Lightbox/空白间隙 | 动效 |
| 🟡 P2 | 优化 3-5: 布局抖动/全量重建 | 性能 |
| 🟢 P3 | 优化 6-9: CSS 死代码清理/变量合并 | 性能 |
| 🟢 P3 | 交互 1-7: 小交互优化/无障碍 | 交互 |

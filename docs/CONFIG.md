# InkMoment 配置项

> 本文对应 `server/settings.py`。运行时优先读取环境变量，其次读取
> `~/.config/inkmoment/settings.toml`，最后使用代码默认值。环境变量优先级最高，
> 便于 Tauri sidecar、CI、测试和临时排障覆盖本机设置。

## settings.toml 示例

```toml
[app]
script_token = "local-script-token"
dev_origins = ["http://localhost:5173"]
legacy_ui = false

[auth]
server_url = "https://auth.example.com"
device_id = "optional-test-device"
app_version = "0.1.0"

[storage]
state_db = "~/Library/Application Support/InkMoment/inkmoment.sqlite3"

[models]
cache_dir = "~/Library/Application Support/InkMoment/models"
no_mirror = false
hf_endpoint = "https://huggingface.co"

[llm]
base_url = "https://ark.cn-beijing.volces.com/api/v3"
timeout = 30
model_check_timeout = 15
model_check_workers = 8
max_workers = 20
pro_max_workers = 1
initial_concurrency = 8
tycoon_analysis_workers = 1
```

`llm.api_key` 虽然能被 `Settings` 读取用于诊断和测试，但不建议写入
`settings.toml`。运行时优先使用 `ARK_API_KEY` 环境变量；通过界面保存的
Key 会优先写入系统 Keyring（macOS Keychain / Windows Credential Manager /
Linux Secret Service），Keyring 不可用时才退回 `~/.config/inkmoment/ark_key`
文件 fallback。启动时如果发现 legacy 明文文件且 Keyring 可用，会迁移到
Keyring 并删除旧文件。

## 环境变量

| 变量 | settings.toml | 默认值 | 作用域 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `INKMOMENT_TOKEN` | `app.script_token` | 空 | Flask sidecar | 开启脚本访问 token，浏览器外 POST 请求需传 `X-Token` 或 `?token=`。 |
| `INKMOMENT_DEV_ORIGINS` | `app.dev_origins` | 空 | Flask sidecar | 逗号分隔的开发源白名单，例如 `http://localhost:5173`。 |
| `INKMOMENT_LEGACY_UI` | `app.legacy_ui` | `false` | Flask sidecar | 旧 UI 回滚开关；当前旧静态入口已下线，仅保留配置兼容。 |
| `INKMOMENT_AUTH_SERVER_URL` | `auth.server_url` | 空 | 授权服务 | 为空时核心 `/api/*` 会以未配置授权服务拒绝访问。 |
| `INKMOMENT_DEVICE_ID` | `auth.device_id` | 自动生成 | 授权服务 | 测试或受控环境可固定设备指纹。 |
| `INKMOMENT_APP_VERSION` | `auth.app_version` | `dev` | 授权服务 | 上报给授权服务的桌面端版本。 |
| `INKMOMENT_STATE_DB` | `storage.state_db` | 平台状态目录 | SQLite | 指定本地轻量数据库路径。 |
| `INKMOMENT_MODEL_CACHE_DIR` | `models.cache_dir` | 平台状态目录下 `models` | 模型依赖 | 指定 HuggingFace / Torch 模型缓存根目录。 |
| `INKMOMENT_NO_MIRROR` | `models.no_mirror` | `false` | 模型下载 | 为真时不自动使用 HuggingFace 镜像。 |
| `HF_ENDPOINT` | `models.hf_endpoint` | 由 vision 层决定 | 模型下载 | 指定 HuggingFace endpoint。 |
| `ARK_API_KEY` | `llm.api_key` | 空 | 土豪模式 LLM | API Key；环境变量优先。界面保存会优先进入系统 Keyring，文件仅作为 headless fallback。 |
| `ARK_BASE_URL` | `llm.base_url` | LLM 默认服务地址 | 土豪模式 LLM | OpenAI 兼容接口根地址，空路径会补 `/v1`。 |
| `ARK_TIMEOUT` | `llm.timeout` | `30` | 土豪模式 LLM | 单次 LLM 请求超时秒数。 |
| `ARK_MODEL_CHECK_TIMEOUT` | `llm.model_check_timeout` | `15` | 土豪模式 LLM | 模型可用性探测超时秒数。 |
| `ARK_MODEL_CHECK_WORKERS` | `llm.model_check_workers` | `8` | 土豪模式 LLM | 模型探测并发数。 |
| `ARK_MAX_WORKERS` | `llm.max_workers` | 空 | 土豪模式 LLM | 全局 LLM 并发上限；设置后覆盖模型推荐值。 |
| `ARK_PRO_MAX_WORKERS` | `llm.pro_max_workers` | `1` | 土豪模式 LLM | Pro 模型并发上限。 |
| `ARK_INITIAL_CONCURRENCY` | `llm.initial_concurrency` | `8` | 土豪模式 LLM | 自适应限流器初始并发。 |
| `INKMOMENT_TYCOON_ANALYSIS_WORKERS` | `llm.tycoon_analysis_workers` | `1` | 土豪模式本地分析 | 大模型筛图本地视觉分析线程数；只影响 DINOv2 / InsightFace / RAW 读取阶段，不影响 LLM HTTP 限速器。 |
| `INKMOMENT_TORCH_THREADS` | 无 | `1` | 本地视觉栈 | Torch intra-op 线程数排障开关；用于降低打包版 macOS native 线程池冲突风险。 |
| `INKMOMENT_TORCH_INTEROP_THREADS` | 无 | `1` | 本地视觉栈 | Torch inter-op 线程数排障开关。 |

## 变更边界

- 轻量数据库仍使用 SQLite，没有改表结构。
- 当前只集中读取配置，不改变授权、模型下载、LLM 调用和发布协议。
- API Key 明文文件只作为 Keyring 不可用时的 fallback；Keyring 可用时会自动迁移并删除 legacy 文件。
- Rust/Tauri 侧仍可直接读取桌面启动相关环境变量，避免 Python 设置模块反向耦合桌面壳。

# 运行与复现

## 评审直接体验

打开 <https://synkore-tuojing.azuremoon15.chatgpt.site>。在线版由服务端管理 MiMo，不需要提交者提供浏览器密钥。使用新版 Chrome、Edge 或 Safari；录音需要 HTTPS 和麦克风授权。在线版每段音频最多 5 分钟，长课请下载 Windows 版。

在线版和桌面版共用 `desktop/frontend`。云端接口为 `cloud/api.mjs`；桌面接口为 `desktop/backend/app`。云端用户资料按服务端签名的匿名 Cookie 隔离，不根据客户端的 `user_id` 授权访问；输入音频仅用于当次处理，不保存为公开文件。浏览器笔记保存在当前浏览器，生成音频只允许同一会话读取。

## 环境

- Node.js 24（最低 22.13）；依赖由两个 `package-lock.json` 锁定。
- Python 3.12（Windows 后端／构建）；根依赖固定在 `desktop/backend/requirements.txt`。
- 云端：Cloudflare Workers、D1、R2；当前通过 Sites 发布。
- 硬件：TuyaOpen SDK，实测提交 `695e571fb4f62932dbf86a86fde664fcb7f2c0b4`。详见 [HARDWARE.md](HARDWARE.md)。

## 云端源码本地启动

在仓库根目录执行：

```bash
npm ci
npm ci --prefix desktop
npm test
npm run build
```

复制 `.dev.vars.example` 为 `.dev.vars`，填入自己的 MiMo 密钥和随机会话签名串。不要提交 `.dev.vars`。仅首次启动时执行数据库初始化：

```bash
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_big_toad.sql
npm start
```

访问命令打印的本机地址。修改代码后重新 `npm run build`，或使用 `npm run dev`；开发与已构建预览都使用 `.wrangler/state`。不要重复执行已经应用的数据库迁移。

## 云端部署

`.openai/hosting.json` 声明当前 Site ID 及 `DB`、`BUCKET` 绑定；其中不含秘密。复用本项目部署时由有权限的维护者通过 Sites 保存并部署源码版本；在自己的账号部署应创建自己的项目，不能挪用本项目 ID。

必需的服务端秘密：

| 名称 | 用途 |
| --- | --- |
| `MIMO_API_KEY` | MiMo ASR、改写、画像与可选播报 |
| `SESSION_SECRET` | 匿名会话 Cookie 的 HMAC 签名；至少32字节随机材料 |
| `CLOUD_DAILY_LIMIT` | 全站每天允许的模型请求数，默认600 |
| `VISITOR_DAILY_LIMIT` | 访客来源每天模型请求数，默认120 |

API 每次模型调用先在 D1 原子计数，超过额度返回明确提示。第三方模型失败不展示虚构结果；公式或条件检查失败则保留原文。音频播报需要与文本核对通过，否则只返回文字。

如使用自己的 Cloudflare 账号，也可将构建得到的 Worker 与 `dist/client` 静态资源部署，配置 `DB`、`BUCKET`，按顺序应用 `drizzle/` 中的迁移，并设置上述秘密。`dist/server/wrangler.json` 中的本机占位数据库 ID 不能直接用于真实生产数据库。

## Windows 源码构建

在 Windows、Python 3.12、Node.js 24 环境下：

```powershell
cd desktop
npm ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe scripts/build-desktop.py
```

生成 `desktop/release/Synkore-Tuojing-1.6.0-Windows-x64/`。整个文件夹必须一起分发，不能只复制 EXE。`docs/ci/validate.yml` 提供可选的自动构建模板；拥有 workflow 权限的维护者可将其放到 `.github/workflows/` 启用。

开发时可单独运行后端：设置 `DATA_DIR`、`MIMO_API_KEY`、`COURSE_WEB_DIR` 等环境变量，再启动 `desktop/backend/run_backend.py`；生产发布推荐直接使用桌面壳，由其选择空闲本机端口、管理访问令牌和进程。

## 测试

- `npm test`：云端音频格式、公式保护、会话隔离、跨域拒绝、失败信息及额度控制。
- `cd desktop` 后运行 `python -m pytest backend/tests -q`：桌面后端回归。
- `cd desktop` 后运行 `node node_modules/playwright/cli.js test`：需要安装 Chrome 和后端测试依赖。测试专用服务不会进入发布包。

## 保留配置与数据

Windows 版将配置保存在 `%APPDATA%\Synkore`，密钥由当前 Windows 账户加密。产品显示名改为「synkore·拓境」，内部存储目录保持稳定以兼容旧版。发布包不包含本机配置或私人数据。

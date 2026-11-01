# 第三方组件与资料来源

本项目沿用以下运行组件；源码依赖版本分别见两个 `package-lock.json` 与 `desktop/backend/requirements.txt`。不要以本项目原创声明覆盖第三方的许可证。

| 组件 | 作用／来源 | 许可证或说明 |
| --- | --- | --- |
| [Electron](https://github.com/electron/electron) 45.2.1 | Windows 桌面壳 | MIT；分发中保留 Electron／Chromium LICENSE 文件 |
| [Three.js](https://github.com/mrdoob/three.js) 0.187.0 | 3D 幽灵与 GLTF 加载 | MIT |
| [Lucide](https://github.com/lucide-icons/lucide) | UI 图标 | ISC |
| [Vite](https://github.com/vitejs/vite) | 前端构建 | MIT |
| [FastAPI](https://github.com/fastapi/fastapi)、[Uvicorn](https://github.com/encode/uvicorn)、[HTTPX](https://github.com/encode/httpx) | 桌面后端与 HTTP | 分别 MIT、BSD-3-Clause、BSD-3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic)、python-multipart、python-dotenv | 输入验证、上传与环境配置 | 遵循各自包内许可证 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | 音频转换工具定位／分发 | BSD-2-Clause 包装器；FFmpeg 可执行文件另受其构建许可证约束，保留所附说明 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | Windows 后端打包 | GPL-2.0-or-later 与 bootloader 例外，见其官方许可证 |
| [Pillow](https://github.com/python-pillow/Pillow) | 图标构建 | HPND |
| [vinext](https://github.com/cloudflare/vinext)、[React](https://github.com/facebook/react)、Cloudflare Vite Plugin | 云端 Worker 构建与静态资源路由 | 各自 MIT 许可证；其余模板依赖见锁文件 |
| Sites 模板与 `scripts/vite/sites-vite-plugin` | 托管构建集成 | 保留模板附带的 LICENSE 与来源注释 |
| [Drizzle ORM](https://github.com/drizzle-team/drizzle-orm) | D1 数据库迁移生成 | Apache-2.0 |
| [TuyaOpen](https://github.com/tuya/TuyaOpen) | T5 SDK／板级驱动 | SDK与各平台组件遵循仓库许可证；本项目不复制整套SDK |
| LVGL（TuyaOpen 配置使用 v8） | 板端界面与触摸 | MIT；字体与平台组件遵循各自许可证 |
| MiMo API | ASR、改写、画像、可选语音 | 外部模型服务；需要用户或服务端合法配置密钥，不包含模型权重 |

动效参考 Aceternity、Magic UI、shadcn/ui、21st.dev 等公开组件的交互表现，当前角色与动效由 Three.js、CSS、Web Animations API 实现。没有分发付费模板；研究记录见 `desktop/DESIGN.md`。

教师与课程来源见 [SOURCES.md](docs/SOURCES.md)。画像是公开资料启发的设计建议，不是教师本人授权或声音克隆。中文导学为原创示例，未下载并再分发第三方课程视频。

幽灵外形、模型与渲染素材来自本项目的角色设计与制作流程；源文件位于 `desktop/frontend/public/assets` 及 `firmware/src/ghost_assets.c`。教师不使用真人照片或仿本人声音。温柔／灵动声音参考是原创合成音，不是教师音色。

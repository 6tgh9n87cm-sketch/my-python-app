# AGENTS.md — AI 编程助手项目说明书

> 本文件供 AI 编程工具（Codex、Claude Code、Cursor 等）在进入仓库时优先读取，
> 用于快速理解项目结构、命令约定与约束，避免在真实代码库上"瞎猜"。

## 项目概览

- **my-python-app**：Flask 语音对话 Web 应用（NOVA 科幻 AI 人格）。
  前端为静态页面（语音对话 UI），后端通过 OpenAI 兼容接口调用大模型。
- **WSGI 入口**：`app:app`，由 gunicorn 加载（服务端由 systemd 托管，服务名 `myapp`）。
- **部署链路**：GitHub Actions（测试 → 构建 → SSH rsync 增量同步 → 远程安装依赖并重启）。

## 常用命令

```bash
pip install -r requirements.txt   # 安装全部依赖（含开发/测试工具）
pytest --cov=. --cov-report=xml -q # 运行测试并输出覆盖率
ruff check .                      # 静态检查（CI 门槛，必须通过）
python app.py                     # 本地运行，监听 0.0.0.0:8000
```

## 架构与关键文件

| 路径 | 说明 |
|---|---|
| `app.py` | Flask 应用，4 个端点：`GET /`（页面）、`GET /health`（健康检查）、`GET /add`（整数求和示例）、`POST /chat`（大模型对话） |
| `static/index.html` | 前端语音对话界面（含录音/播放逻辑） |
| `tests/test_app.py` | pytest 测试（覆盖 4 个端点） |
| `.github/workflows/ci-cd.yml` | 测试矩阵（Python 3.11–3.13）+ 构建 sdist/wheel + SSH 部署 |
| `.github/workflows/security.yml` | CodeQL / Bandit / gitleaks / pip-audit 四路安全扫描 |
| `scripts/` | 服务器初始化与 HTTPS 配置脚本（服务端使用） |
| `docs/` | 部署与使用文档 |

## 规则与约束

1. **密钥不进仓库**：`LLM_API_KEY` 等敏感配置一律放在服务器 `.env`（由 `_load_env()` 读取），
   永不写入代码或提交仓库。改代码时不得新增硬编码密钥。
2. **LLM 配置走环境变量**：`LLM_API_KEY`、`LLM_BASE_URL`（默认 `https://api.deepseek.com`）、`LLM_MODEL`（默认 `deepseek-chat`）。
3. **/chat 异常处理**：只向前端返回通用提示，完整异常写日志（`logger.exception`），不得暴露堆栈细节。
4. **Python 版本**：CI 矩阵为 3.11–3.13。`pyproject.toml` 中 `requires-python = ">=3.9"` 已过时，
   新代码请按 3.11+ 语法编写，不要引入 3.9 专用写法。
5. **代码风格**：ruff 默认规则。任何改动必须通过 `ruff check .`。
6. **测试纪律**：新增端点必须配套测试（`tests/test_app.py`），保持当前通过状态。
7. **依赖变更**：改依赖时同步更新 `requirements.txt`，并跑一遍 `pip-audit -r requirements.txt --strict`。
8. **服务器配置**：systemd 服务、Nginx 等服务器侧配置不在本仓库管理，提交时不要混入服务器专属文件。

## 建议工作流

1. 动手前先跑 `ruff check .` 与 `pytest` 确认基线为绿色。
2. 小步提交：一次改动配一次验证（lint + 单测）。
3. 涉及接口/依赖/部署链路的改动，在 PR 描述中说明影响面。
4. 推送后确认 CI 三个 job（test / build / deploy）状态，必要时查看 Actions 日志修复。

# Anaagent

**像管理 Python 包一样管理 AI Agent 团队**

Anaagent 是一个 AI Agent 团队管理平台，灵感来自于 Anaconda/Conda 的包管理方式。它让你可以轻松创建、配置和管理多个 AI Agent 团队，每个团队拥有独立的成员、技能、MCP 服务和 Hook。

## 特性

- **Conda 风格 CLI** - 熟悉的命令行体验：`agent create`、`agent activate`、`agent deactivate`
- **团队隔离** - 每个团队独立的配置、成员、技能、MCP 和记忆
- **Shell 集成** - 终端提示符自动显示当前团队 `(team_name)`
- **Claude Code 集成** - Claude 自动了解团队上下文、成员、可用资源
- **Docker 支持** - 一键部署到 Docker 容器，开箱即用
- **灵活配置** - 支持自定义 API Key、Base URL、模型

## 新设备完整流程

在一台**从未配置过**的设备上，从零接上 Anaagent（本地 Docker + 微信小程序绑定），建议严格按顺序执行：

**前置条件：** 已安装 [Node.js](https://nodejs.org/) 与 [Docker](https://docs.docker.com/get-docker/)，本机可正常执行 `docker pull`（如需请先 `docker login`）。

```bash
# 1）安装本地连接器 CLI（可选；跳过则全程使用 npx，无需全局安装）
npm install -g @wuran/local-cli@latest

# 2）拉取镜像并启动本地容器
npx @wuran/local-cli setup

# 3）在微信小程序中刷新页面获取绑定码后执行（将下方替换为实际验证码）
npx @wuran/local-cli connect --code 绑定码

# 4）进入容器终端，使用 agent / Claude 等（可选）
npx @wuran/local-cli console
```

说明：

- 步骤 1 若省略，可直接运行步骤 2–4 中的 `npx @wuran/local-cli ...`。
- **绑定码**由小程序页面刷新后展示；`connect` 成功后会自动拉起本地 WebSocket 中转，并把小程序里保存的 **API Key / Base URL / Model** 同步到容器。
- **默认绑定服务**为 `https://www.winmar.top`，可用环境变量 `ANAAGENT_BIND_SERVER` 指向其它中转地址（例如 PowerShell：`$env:ANAAGENT_BIND_SERVER="https://api.example.com"`）。
- Windows 若 `npm install -g` 报 **EPERM**（无法写入 `Program Files` 下全局目录），可将 npm 全局前缀改到用户目录（如 `npm config set prefix "%APPDATA%\npm"` 并把该路径加入 `PATH`），或**不要全局安装**，仅用上面的 `npx` 命令。

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 拉取镜像
docker pull kerwinnnn/anaagent:latest

# 运行容器
docker run -d --name anaagent-cli \
  -v anaagent-data:/root/.anaagent \
  --restart unless-stopped \
  --entrypoint "" \
  kerwinnnn/anaagent:latest sleep infinity

# 进入容器
docker exec -it anaagent-cli bash
```

### 方式二：本地安装

```bash
# 克隆仓库
git clone https://github.com/winmarWu/Anaagent.git
cd Anaagent

# 安装依赖
pip install -e .

# 开始使用
agent --help
```

### 方式三：npm 一行命令连接本地 Docker（小程序绑定）

**从零开始的推荐顺序**见上文 **[新设备完整流程]**。日常可单独使用下列命令：

```bash
# 创建/启动本地 docker 环境
npx @wuran/local-cli setup

# 小程序刷新后拿到绑定码（例如 A1B2C3），本地连接
npx @wuran/local-cli connect --code A1B2C3

# 查询绑定状态（可选）
npx @wuran/local-cli status

# 进入本地管理后台 / 容器 shell（可选）
npx @wuran/local-cli console
```

默认绑定服务地址：`https://www.winmar.top`。可用环境变量覆盖：

```bash
# PowerShell
$env:ANAAGENT_BIND_SERVER="https://api.example.com"
```

说明：`connect` 成功后会自动拉起本地 WebSocket 中转，无需额外执行 `client-v4.js start`。
同时会自动同步小程序端保存的 `API Key / Base URL / Model` 到本地容器配置。

## 基本使用

### 团队管理

```bash
# 创建新团队
agent create my-team

# 列出所有团队
agent list

# 激活团队
agent activate my-team

# 退出团队
agent deactivate

# 删除团队
agent remove my-team
```

### 配置管理

```bash
# 设置 base 环境默认配置（创建团队时使用）
agent config set-base

# 设置当前团队的 Claude 配置
agent config set-team

# 查看当前团队配置
agent config show-team

# 刷新环境变量（修改配置后）
agent refresh
```

### 成员管理

```bash
# 添加成员
agent member add alice --role developer

# 列出成员
agent member list

# 删除成员
agent member remove alice
```

### 组件管理

```bash
# 列出已安装组件
agent list-components          # 列出所有
agent list-components skills   # 仅列出技能
agent list-components mcps     # 仅列出 MCP
agent list-components hooks    # 仅列出 Hook

# 安装组件
agent install skill/web-search
agent install mcp/filesystem
agent install hook/logger
```

### 市场功能

```bash
# 查看市场
agent market list

# 搜索
agent market search web

# 从市场安装
agent market install skill web-search
```

### 记忆管理

```bash
# 添加记忆
agent memory add "用户偏好使用中文回复"

# 搜索记忆
agent memory recall "偏好"

# 显示记忆上下文
agent memory show
```

### 使用统计

```bash
# 今日使用量
agent usage today

# 按成员统计
agent usage stats
```

## Claude Code 集成

激活团队后，直接运行 `claude` 即可：

```bash
agent activate my-team
claude
```

Claude 会自动：
- 显示团队信息横幅
- 读取 `CLAUDE.md` 了解团队上下文
- 知道当前团队的成员、技能、MCP、Hook
- 使用团队配置的 API Key 和模型

## 工作流程示例

```bash
# 1. 进入容器
docker exec -it anaagent-cli bash

# 2. 创建并激活团队
(base) root@container:~# agent create my-project
(base) root@container:~# agent activate my-project

# 3. 提示符变为团队名
(my-project) root@container:~/.anaagent/.../workspace/projects#

# 4. 配置团队
(my-project) root@...# agent config set-team
# 输入 API Key、Base URL、Model

# 5. 刷新环境
(my-project) root@...# agent refresh

# 6. 添加成员
(my-project) root@...# agent member add dev1

# 7. 启动 Claude
(my-project) root@...# claude

# 8. 退出团队
(my-project) root@...# agent deactivate
(base) root@container:~#
```

## 项目结构

```
~/.anaagent/
├── base_config.json          # Base 环境默认配置
├── active_env                # 当前激活的团队
├── environments/             # 所有团队
│   ├── team-a/
│   │   ├── team.yaml         # 团队配置
│   │   ├── .claude/          # Claude 配置
│   │   │   └── settings.json
│   │   ├── agents/           # 成员配置
│   │   ├── skills/           # 技能
│   │   ├── mcps/             # MCP 服务
│   │   ├── hooks/            # Hook 脚本
│   │   ├── memory/           # 团队记忆
│   │   └── workspace/        # 工作目录
│   │       └── projects/
│   │           └── CLAUDE.md # 团队上下文
│   └── team-b/
└── marketplace/               # 市场缓存
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_AUTH_TOKEN` | API 密钥 |
| `ANTHROPIC_BASE_URL` | API 基础 URL |
| `ANTHROPIC_MODEL` | 默认模型 |
| `AGENT_ACTIVE_TEAM` | 当前激活的团队名 |
| `ANAAGENT_ENV` | 当前团队路径 |

## 命令速查表

| 命令 | 说明 |
|------|------|
| `agent create <name>` | 创建团队 |
| `agent activate <name>` | 激活团队 |
| `agent deactivate` | 退出团队 |
| `agent list` | 列出团队 |
| `agent remove <name>` | 删除团队 |
| `agent info` | 团队信息 |
| `agent refresh` | 刷新环境变量 |
| `agent member add/remove/list` | 成员管理 |
| `agent config set-team/show-team` | 配置管理 |
| `agent list-components` | 列出组件 |
| `agent install <type>/<name>` | 安装组件 |
| `agent market list/search/install` | 市场功能 |
| `agent memory add/recall/show` | 记忆管理 |
| `agent usage today/stats` | 使用统计 |

## 支持的 API

Anaagent 支持任何兼容 Anthropic API 的服务：

- **Anthropic Claude** - 默认支持
- **其他兼容服务** - 自定义 Base URL 即可

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

---

**Anaagent** - 让 AI Agent 团队管理变得简单
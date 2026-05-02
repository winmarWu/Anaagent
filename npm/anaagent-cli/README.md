# @wuran/local-cli

Anaagent 的本地 Docker 连接器 CLI，用于实现：

- 一行命令初始化本地运行环境
- 一行命令启动本地容器
- 与小程序验证码绑定本地节点

## Quick Start

```bash
npx @wuran/local-cli setup
```

若希望容器内的 `agent` 与当前 Anaagent 源码一致（例如 `agent list` 含 **Team Type** 列、最新的 `team_type` 规范化），在**本仓库根目录与 `npm/anaagent-cli` 的相对位置不变**的前提下执行一次：

```bash
npx @wuran/local-cli install-dev
```

源码不在默认相对路径时：

```bash
npx @wuran/local-cli install-dev --src D:/path/to/Anaagent
```

**说明：** 每次 `setup` 若重建了容器，需要重新执行 `install-dev`。官方镜像自带的 `anaagent` 不会自动包含你 Git 里未发布的改动。

## 绑定流程

```bash
# 1) 小程序刷新后拿到绑定码 A1B2C3（由你们现有服务完成）
# 2) 本地一行命令完成连接
npx @wuran/local-cli connect --code A1B2C3

# 3) 查询状态（会显示 LocalClient 在线数）
npx @wuran/local-cli status

# 4) 打开容器管理后台（可选）
npx @wuran/local-cli console
```

`connect` 成功后会自动启动本地 WebSocket 中转守护进程，无需再手动运行 `client-v4.js`。
并会定期从服务端拉取用户设置（`ANTHROPIC_AUTH_TOKEN/BASE_URL/MODEL`）写入本地容器配置。

默认绑定服务地址为 `https://www.winmar.top`，也可以覆盖：

```bash
# PowerShell
$env:ANAAGENT_BIND_SERVER="https://api.example.com"
npx @wuran/local-cli connect --code A1B2C3
```

## Commands

- `setup` - 一行完成拉镜像、创建 volume、启动容器
- `install-dev [--src PATH]` - 将宿主机 Anaagent 拷入容器并 `pip install -e`（与仓库 CLI 行为一致）
- `init` - 拉取镜像并创建 volume/workspace
- `start` - 启动本地容器
- `connect --code CODE [--server URL]` - 按绑定码连接小程序账户
- `shell` - 进入容器终端
- `console` - `shell` 的别名
- `stop` - 停止并删除容器
- `logs` - 查看容器日志
- `code-refresh --user-id ID [--ttl 90]` - 本地调试签发一次性验证码
- `bind --code CODE [--device-name NAME] [--device-id ID]` - 绑定本地节点
- `status [--server URL]` - 查询当前连接状态
- `device-id` - 查看本地持久设备身份
- `bridge-stop` - 停止本地中转守护进程
- `--local true` - 强制使用本地 sqlite 绑定逻辑（调试用）

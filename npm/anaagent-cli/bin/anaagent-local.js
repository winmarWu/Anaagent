#!/usr/bin/env node

import { randomUUID } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const IMAGE = process.env.ANAAGENT_IMAGE || "kerwinnnn/anaagent:latest";
const CONTAINER = process.env.ANAAGENT_CONTAINER || "anaagent-cli";
const VOLUME = process.env.ANAAGENT_VOLUME || "anaagent-data";
const DEFAULT_BIND_SERVER = "https://www.winmar.top";
const BIND_SERVER = process.env.ANAAGENT_BIND_SERVER || "";
const CLI_FILE = fileURLToPath(import.meta.url);

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: false,
    windowsHide: true,
    ...options
  });
  if (result.error) {
    throw result.error;
  }
  if (typeof result.status === "number" && result.status !== 0) {
    process.exit(result.status);
  }
}

function capture(command, args) {
  const result = spawnSync(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    encoding: "utf-8",
    shell: false,
    windowsHide: true
  });
  if (result.error) {
    throw result.error;
  }
  return {
    status: result.status ?? 1,
    stdout: (result.stdout || "").trim(),
    stderr: (result.stderr || "").trim()
  };
}

function captureAsync(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      ...options
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk || "");
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk || "");
    });
    child.on("error", (error) => reject(error));
    child.on("close", (code) => {
      resolve({
        status: typeof code === "number" ? code : 1,
        stdout: String(stdout || "").trim(),
        stderr: String(stderr || "").trim()
      });
    });
  });
}

function parseOptions(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) {
      continue;
    }
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      options[key] = "true";
      continue;
    }
    options[key] = next;
    i += 1;
  }
  return options;
}

function requireOption(options, key) {
  const value = options[key];
  if (!value) {
    console.error(`Missing required option: --${key}`);
    process.exit(1);
  }
  return String(value);
}

function isTruthy(value) {
  return String(value || "").toLowerCase() === "true";
}

function normalizeServerBase(url) {
  return String(url || "").trim().replace(/\/+$/, "");
}

function resolveServer(options) {
  const fromFlag = String(options.server || "").trim();
  return normalizeServerBase(fromFlag || BIND_SERVER || DEFAULT_BIND_SERVER);
}

function getOrCreateLocalDeviceIdentity(deviceName = "") {
  const dir = path.join(homedir(), ".anaagent");
  const file = path.join(dir, "local-cli-device.json");
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  if (existsSync(file)) {
    try {
      const payload = JSON.parse(readFileSync(file, "utf-8"));
      if (payload.device_id) {
        if (deviceName && payload.device_name !== deviceName) {
          payload.device_name = deviceName;
          writeFileSync(file, JSON.stringify(payload, null, 2), "utf-8");
        }
        return payload;
      }
    } catch {
      // fallthrough to recreate
    }
  }

  const payload = {
    device_id: randomUUID(),
    device_name: deviceName || "",
    created_at: new Date().toISOString()
  };
  writeFileSync(file, JSON.stringify(payload, null, 2), "utf-8");
  return payload;
}

function getAuthFilePath() {
  return path.join(homedir(), ".anaagent", "local-cli-auth.json");
}

function getBridgeStatePath() {
  return path.join(homedir(), ".anaagent", "local-cli-bridge.json");
}

function saveAuthInfo(payload) {
  const dir = path.join(homedir(), ".anaagent");
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  writeFileSync(getAuthFilePath(), JSON.stringify(payload, null, 2), "utf-8");
}

function loadAuthInfo() {
  const file = getAuthFilePath();
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, "utf-8"));
  } catch {
    return null;
  }
}

function saveBridgeState(payload) {
  const dir = path.join(homedir(), ".anaagent");
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  writeFileSync(getBridgeStatePath(), JSON.stringify(payload, null, 2), "utf-8");
}

function loadBridgeState() {
  const file = getBridgeStatePath();
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, "utf-8"));
  } catch {
    return null;
  }
}

function removeBridgeState() {
  const file = getBridgeStatePath();
  if (existsSync(file)) {
    try {
      writeFileSync(file, "{}", "utf-8");
    } catch {
      // ignore
    }
  }
}

function buildWsUrl(serverBase, token) {
  const base = new URL(serverBase);
  const proto = base.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${base.host}/ws?type=local&token=${encodeURIComponent(token)}`;
}

function killBridgeIfRunning() {
  const state = loadBridgeState();
  const pid = Number(state?.pid || 0);
  if (!pid) return;
  try {
    process.kill(pid);
  } catch {
    // already dead
  }
}

function startBridgeDaemon(server, token, userId) {
  killBridgeIfRunning();
  const child = spawn(
    process.execPath,
    [CLI_FILE, "bridge-runner", "--server", server, "--token", token, "--user-id", userId],
    {
      detached: true,
      stdio: "ignore",
      windowsHide: true
    }
  );
  child.unref();
  saveBridgeState({
    pid: child.pid,
    server,
    userId,
    startedAt: new Date().toISOString()
  });
  return child.pid;
}

async function requestJson(url, method, payload = null, extraHeaders = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", ...extraHeaders },
      body: payload ? JSON.stringify(payload) : undefined,
      signal: controller.signal
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    if (!response.ok) {
      const msg = data.error || data.reason || `${response.status} ${response.statusText}`;
      throw new Error(msg);
    }
    if (typeof data === "object" && data !== null && Object.prototype.hasOwnProperty.call(data, "success")) {
      if (!data.success) {
        const msg = data.error?.message || data.error?.code || "request failed";
        throw new Error(msg);
      }
    }
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function ensureDocker() {
  const docker = capture("docker", ["--version"]);
  if (docker.status !== 0) {
    console.error("Docker is not available. Install Docker Desktop first.");
    process.exit(1);
  }
}

/** 与本 CLI 同仓库的 Anaagent 根目录（…/Anaagent/npm/anaagent-cli/bin → 上三级） */
function defaultAnaagentRepoRoot() {
  return path.resolve(path.dirname(CLI_FILE), "..", "..", "..");
}

/**
 * 将宿主机 Anaagent 源码拷入容器并 pip install -e，使 agent list 含 Team Type、normalize_team_type 等与仓库一致。
 * 重建容器或换新镜像后需重新执行；与团队类型是否在小程显示无关（后者依赖绑定服务 API）。
 */
function installDevAnaagentInContainer(repoRoot) {
  const abs = path.resolve(repoRoot);
  const marker = path.join(abs, "pyproject.toml");
  if (!existsSync(marker)) {
    console.error(
      "未找到 Anaagent Python 包根目录（缺少 pyproject.toml）：\n" +
        `  ${abs}\n` +
        "若 npm 包不在本仓库内，请指定：install-dev --src <Anaagent 根目录>"
    );
    process.exit(1);
  }
  ensureContainerStarted();
  capture("docker", ["exec", CONTAINER, "rm", "-rf", "/tmp/anaagent-repo"]);
  const cpResult = capture("docker", ["cp", abs, `${CONTAINER}:/tmp/anaagent-repo`]);
  if (cpResult.status !== 0) {
    console.error("docker cp 失败:", cpResult.stderr || cpResult.stdout || cpResult.error);
    process.exit(cpResult.status || 1);
  }
  run("docker", [
    "exec",
    "-i",
    CONTAINER,
    "python",
    "-m",
    "pip",
    "install",
    "-e",
    "/tmp/anaagent-repo"
  ]);
  console.log("已在容器内 pip install -e /tmp/anaagent-repo。进入 console 后执行 agent list 应含 Team Type 列。");
}

function ensureWorkspaceDir() {
  const workspace = path.resolve(process.cwd(), "workspace");
  if (!existsSync(workspace)) {
    mkdirSync(workspace, { recursive: true });
  }
  return workspace;
}

function containerExists() {
  const result = capture("docker", ["ps", "-a", "--filter", `name=^${CONTAINER}$`, "--format", "{{.Names}}"]);
  return result.status === 0 && result.stdout.split("\n").includes(CONTAINER);
}

function containerRunning() {
  const result = capture("docker", ["ps", "--filter", `name=^${CONTAINER}$`, "--format", "{{.Names}}"]);
  return result.status === 0 && result.stdout.split("\n").includes(CONTAINER);
}

function ensureContainerStarted() {
  if (containerRunning()) {
    return;
  }
  if (containerExists()) {
    run("docker", ["start", CONTAINER]);
    return;
  }
  startContainer();
}

function startContainer() {
  const workspaceDir = ensureWorkspaceDir();
  run("docker", ["volume", "create", VOLUME]);
  run("docker", [
    "run",
    "-d",
    "--name",
    CONTAINER,
    "--entrypoint",
    "/bin/sh",
    "-v",
    `${VOLUME}:/root/.anaagent`,
    "-v",
    `${workspaceDir}:/workspace`,
    "-w",
    "/workspace",
    "--restart",
    "unless-stopped",
    IMAGE,
    "-c",
    "sleep infinity"
  ]);
}

function runAgentTask(taskArgs) {
  ensureContainerStarted();
  run("docker", ["exec", "-i", CONTAINER, "agent", "task", ...taskArgs]);
}

function execInContainer(command) {
  ensureContainerStarted();
  return capture("docker", ["exec", "-i", CONTAINER, "/bin/sh", "-c", command]);
}

function ensureWorkflowRuntimeDependencies() {
  ensureContainerStarted();
  const checkScript = `
import importlib.util
modules = {
    "langgraph": "langgraph>=0.2.0",
    "anthropic": "anthropic>=0.39.0",
    "pytest": "pytest>=7.0.0",
}
missing_packages = []
for module_name, package_name in modules.items():
    if importlib.util.find_spec(module_name) is None:
        missing_packages.append(package_name)
print(" ".join(missing_packages))
`;
  const check = capture("docker", ["exec", "-i", CONTAINER, "python", "-c", checkScript]);
  const missingPackages = String(check.stdout || "").trim();
  if (!missingPackages) {
    return;
  }

  const packages = missingPackages.split(/\s+/).filter(Boolean);
  if (!packages.length) return;

  console.log(`检测到容器缺少依赖: ${packages.join(", ")}，正在自动安装...`);
  const install = capture("docker", [
    "exec",
    "-i",
    CONTAINER,
    "python",
    "-m",
    "pip",
    "install",
    "--no-cache-dir",
    ...packages
  ]);
  if (install.status !== 0) {
    const detail = install.stderr || install.stdout || "unknown pip error";
    throw new Error(`自动安装依赖失败: ${detail}`);
  }
  console.log("工作流依赖安装完成。");
}

function getLocalTeamsForSync() {
  ensureContainerStarted();
  const py = `
import glob
import json
from pathlib import Path
try:
    import yaml
except Exception:
    yaml = None

root = Path('/root/.anaagent/environments')
active = ''
active_file = Path('/root/.anaagent/active_env')
if active_file.exists():
    try:
        active = active_file.read_text(encoding='utf-8').strip()
    except Exception:
        active = ''

teams = []
if root.exists():
    for env_dir in root.iterdir():
        if not env_dir.is_dir():
            continue
        name = env_dir.name
        created_at = ''
        description = ''
        team_type = 'software_dev'
        team_yaml = env_dir / 'team.yaml'
        if yaml is not None and team_yaml.exists():
            try:
                data = yaml.safe_load(team_yaml.read_text(encoding='utf-8')) or {}
            except Exception:
                data = {}
            created_at = str(data.get('created_at') or '')
            description = str(data.get('description') or '')
            try:
                from anaagent.config_manager import normalize_team_type as _norm_tt
                team_type = _norm_tt(
                    str(data.get('team_type') or data.get('teamType') or '') or None
                )
            except Exception:
                team_type = str(data.get('team_type') or data.get('teamType') or 'software_dev')
        members = []
        agents_dir = env_dir / 'agents'
        if agents_dir.exists():
            for f in agents_dir.glob('*.yaml'):
                members.append({
                    'id': f.stem,
                    'name': f.stem,
                    'role': 'assistant',
                    'model': 'claude-sonnet-4-6',
                    'status': 'online'
                })
        teams.append({
            'name': name,
            'description': description,
            'createdAt': created_at,
            'teamType': team_type,
            'team_type': team_type,
            'isActive': name == active,
            'memberCount': len(members),
            'members': members
        })

print(json.dumps(teams, ensure_ascii=False))
`;

  const result = capture("docker", ["exec", "-i", CONTAINER, "python", "-c", py]);
  if (result.status !== 0) return [];
  try {
    return JSON.parse(result.stdout || "[]");
  } catch {
    return [];
  }
}

/**
 * 团队类型在后端/小程序里字段名不统一；尽量兼容多种键名。
 * 若仍得不到值则回退 software_dev（常见于绑定服务未在 pending/teams 里持久化 teamType）。
 */
function pickPendingTeamType(item) {
  if (!item || typeof item !== "object") return "software_dev";
  const c = item;
  const fromStr =
    c.teamType ??
    c.team_type ??
    c.type ??
    c.category ??
    c.teamKind ??
    c.teamCategory;
  if (fromStr !== undefined && fromStr !== null && String(fromStr).trim() !== "") {
    return String(fromStr).trim();
  }
  const idx = c.teamTypeIndex ?? c.team_type_index ?? c.typeIndex ?? c.teamTypeIdx;
  if (typeof idx === "number" && Number.isFinite(idx)) {
    const map = ["software_dev", "article_writing", "research_assistant"];
    if (idx >= 0 && idx < map.length) return map[idx];
  }
  if (typeof idx === "string" && /^\d+$/.test(idx)) {
    const n = parseInt(idx, 10);
    const map = ["software_dev", "article_writing", "research_assistant"];
    if (n >= 0 && n < map.length) return map[n];
  }
  return "software_dev";
}

function printHelp() {
  console.log(`
Anaagent Local CLI

Usage:
  npx @wuran/local-cli <command> [options]

Commands:
  setup                        Pull image, create volume, and start container
  init                         Pull image and prepare local volume/workspace
  start                        Start local docker connector container
  install-dev [--src PATH]     Copy Anaagent repo into container; pip install -e (agent list Team Type, etc.)
  connect --code CODE          Bind local node with mini-program binding code
  shell                        Enter docker shell
  console                      Alias of shell, open management console
  stop                         Stop local container
  logs                         Show container logs
  code-refresh --user-id ID    Generate one-time binding code
  bind --code CODE             Bind current local node with mini-program code
  status                       Query current connection status
  device-id                    Show persistent local device identity
  bridge-stop                  Stop local websocket bridge daemon

Examples:
  npx @wuran/local-cli setup
  npx @wuran/local-cli connect --code A1B2C3
  npx @wuran/local-cli console
  npx @wuran/local-cli status

Bind Server:
  default: https://www.winmar.top
  --server https://api.example.com   # 覆盖默认地址
  ANAAGENT_BIND_SERVER=...           # 覆盖默认地址
  --local true  # Force local sqlite mode
`);
}

async function main() {
  const [, , command = "help", ...rest] = process.argv;
  const options = parseOptions(rest);

  if (command === "bridge-runner") {
    const server = requireOption(options, "server");
    const token = requireOption(options, "token");
    const userId = String(options["user-id"] || "");
    await runBridgeLoop(server, token, userId);
    return;
  }

  if (command === "help" || command === "--help" || command === "-h") {
    printHelp();
    return;
  }

  ensureDocker();

  switch (command) {
    case "setup":
      ensureWorkspaceDir();
      run("docker", ["pull", IMAGE]);
      run("docker", ["volume", "create", VOLUME]);
      if (containerExists()) {
        if (containerRunning()) {
          run("docker", ["stop", CONTAINER]);
        }
        run("docker", ["rm", CONTAINER]);
      }
      ensureContainerStarted();
      console.log("Anaagent local runtime is ready.");
      return;
    case "init":
      ensureWorkspaceDir();
      run("docker", ["pull", IMAGE]);
      run("docker", ["volume", "create", VOLUME]);
      console.log("Anaagent local runtime initialized.");
      return;
    case "start":
      ensureContainerStarted();
      console.log(`Container '${CONTAINER}' is running.`);
      return;
    case "install-dev": {
      const src = options.src ? String(options.src) : "";
      const repo = src ? path.resolve(src) : defaultAnaagentRepoRoot();
      installDevAnaagentInContainer(repo);
      return;
    }
    case "shell":
      ensureContainerStarted();
      run("docker", ["exec", "-it", CONTAINER, "/bin/bash"]);
      return;
    case "console":
      ensureContainerStarted();
      run("docker", ["exec", "-it", CONTAINER, "/bin/bash"]);
      return;
    case "stop":
      if (!containerExists()) {
        console.log(`Container '${CONTAINER}' does not exist.`);
        return;
      }
      run("docker", ["stop", CONTAINER]);
      run("docker", ["rm", CONTAINER]);
      console.log(`Container '${CONTAINER}' stopped and removed.`);
      return;
    case "logs":
      ensureContainerStarted();
      run("docker", ["logs", "-f", CONTAINER]);
      return;
    case "code-refresh": {
      const userId = requireOption(options, "user-id");
      const ttl = options.ttl ? String(options.ttl) : "90";
      const localMode = isTruthy(options.local);
      const server = resolveServer(options);
      if (server && !localMode) {
        console.log(`Server mode active (${server}).`);
        console.log("请在小程序端刷新绑定码，当前服务端不开放本地刷新接口。");
        console.log(`可使用本地模式测试: npx @wuran/local-cli code-refresh --user-id ${userId} --local true --ttl ${ttl}`);
        return;
      }
      runAgentTask(["code-refresh", "--user-id", userId, "--ttl", ttl]);
      return;
    }
    case "bind": {
      const code = requireOption(options, "code");
      const args = ["bind", "--code", code];
      if (options["device-name"]) {
        args.push("--device-name", String(options["device-name"]));
      }
      if (options["device-id"]) {
        args.push("--device-id", String(options["device-id"]));
      }
      runAgentTask(args);
      return;
    }
    case "connect": {
      const code = requireOption(options, "code");
      const localMode = isTruthy(options.local);
      const server = resolveServer(options);
      if (server && !localMode) {
        ensureContainerStarted();
        const payload = { bindCode: code.toUpperCase() };
        const result = await requestJson(
          `${server}/api/auth/connect`,
          "POST",
          payload
        );
        const data = result.data || {};
        const token = String(data.token || "");
        const userId = String(data.userId || "");
        if (!token || !userId) {
          throw new Error("server returned empty token/userId");
        }
        saveAuthInfo({
          server,
          userId,
          token,
          bindCode: data.bindCode || payload.bindCode,
          updatedAt: new Date().toISOString()
        });
        const bridgePid = startBridgeDaemon(server, token, userId);
        console.log("Connected successfully.");
        console.log(`User ID: ${userId}`);
        console.log(`Bind Code: ${data.bindCode || payload.bindCode}`);
        console.log(`Server: ${server}`);
        console.log(`Local bridge pid: ${bridgePid}`);
        console.log("下一步: 运行 npx @wuran/local-cli console 进入容器管理后台。");
        console.log(
          "若 agent list 缺少 Team Type 列: 在本仓库执行 install-dev（或 setup 后再 install-dev）。"
        );
        return;
      }
      const args = ["bind", "--code", code];
      if (options["device-name"]) {
        args.push("--device-name", String(options["device-name"]));
      }
      if (options["device-id"]) {
        args.push("--device-id", String(options["device-id"]));
      }
      runAgentTask(args);
      return;
    }
    case "status": {
      const localMode = isTruthy(options.local);
      const server = resolveServer(options);
      if (server && !localMode) {
        const auth = loadAuthInfo();
        if (!auth || !auth.token) {
          console.log("未检测到连接凭据，请先执行 connect。");
          return;
        }
        const bridge = loadBridgeState();
        const health = await requestJson(`${server}/health`, "GET");
        const teams = await requestJson(
          `${server}/api/teams`,
          "GET",
          null,
          {
            Authorization: `Bearer ${auth.token}`
          }
        );
        const teamCount = Array.isArray(teams.data) ? teams.data.length : 0;
        console.log("Status:");
        console.log(`  Server: ${server}`);
        console.log(`  User ID: ${auth.userId || "-"}`);
        console.log(`  HTTP: ${health.status === "ok" ? "ok" : "unknown"}`);
        console.log(`  Online local clients: ${health.localClients ?? health.connections?.localClients ?? 0}`);
        console.log(`  Synced teams: ${teamCount}`);
        console.log(`  Bridge PID: ${bridge?.pid || "-"}`);
        return;
      }
      const args = ["bind-status"];
      if (options["user-id"]) {
        args.push("--user-id", String(options["user-id"]));
      }
      if (options["device-id"]) {
        args.push("--device-id", String(options["device-id"]));
      }
      runAgentTask(args);
      return;
    }
    case "device-id":
      runAgentTask(["device-id"]);
      return;
    case "bridge-stop":
      killBridgeIfRunning();
      removeBridgeState();
      console.log("Local websocket bridge stopped.");
      return;
    default:
      console.error(`Unknown command: ${command}`);
      printHelp();
      process.exit(1);
  }
}

async function runBridgeLoop(server, token, userId) {
  const WebSocketClass = globalThis.WebSocket;
  if (!WebSocketClass) {
    throw new Error("Current Node.js runtime does not support WebSocket.");
  }

  const wsUrl = buildWsUrl(server, token);
  let ws = null;
  let heartbeat = null;
  let settingsSyncTimer = null;
  let teamsSyncTimer = null;
  let pendingTeamsSyncTimer = null;
  let lastSettingsSignature = "";
  let workflowDepsReady = false;
  const heartbeatIntervalMs = 30000;
  const settingsSyncIntervalMs = 60000;
  const teamsSyncIntervalMs = 30000;
  const pendingTeamsSyncIntervalMs = 15000;

  const syncSettingsToDocker = async () => {
    try {
      ensureContainerStarted();
      const result = await requestJson(
        `${server}/api/user/settings`,
        "GET",
        null,
        { Authorization: `Bearer ${token}` }
      );
      const data = result?.data || {};
      const anthropicAuthToken = String(data.anthropicAuthToken || data.anthropic_auth_token || "");
      const anthropicBaseUrl = String(data.anthropicBaseUrl || data.anthropic_base_url || "");
      const anthropicModel = String(data.anthropicModel || data.anthropic_model || "");
      const signature = `${anthropicAuthToken}::${anthropicBaseUrl}::${anthropicModel}`;
      if (!signature || signature === "::" || signature === lastSettingsSignature) return;
      lastSettingsSignature = signature;
      applySettingsToDocker(anthropicAuthToken, anthropicBaseUrl, anthropicModel);
    } catch {
      // Ignore transient sync failure, next timer will retry.
    }
  };

  const sendJson = (payload) => {
    if (!ws || ws.readyState !== WebSocketClass.OPEN) return;
    ws.send(JSON.stringify(payload));
  };

  const handleWorkflowRun = async (payload) => {
    const taskId = String(payload?.taskId || "");
    const workflowId = String(payload?.workflowId || `wf_${Date.now()}`);
    const teamId = String(payload?.teamId || "");
    const teamName = String(payload?.teamName || teamId.replace(/^team_/, ""));
    const request = String(payload?.request || "");
    const workflowType = String(payload?.workflowType || "software_company");
    const testCommand = String(payload?.testCommand || "pytest -q || true");
    if (!teamId || !request) return;

    const sendStatus = (stage, status, progress, currentAgent = stage) => {
      sendJson({
        type: "workflow_status",
        messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
        payload: {
          taskId,
          workflowId,
          teamId,
          stage,
          status,
          progress,
          currentAgent
        }
      });
    };

    try {
      if (!workflowDepsReady) {
        ensureWorkflowRuntimeDependencies();
        workflowDepsReady = true;
      }
      sendStatus("pm", "running", 5, "pm");

      const py = `
import subprocess
import sys
from pathlib import Path
from datetime import datetime
request = sys.argv[1]
team_name = sys.argv[2]
workflow_type = sys.argv[3]
test_command = sys.argv[4]
task_id = sys.argv[5]
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
base_name = f"run_{timestamp}"
projects_root = Path(f"/root/.anaagent/environments/{team_name}/workspace/projects")
project_dir = projects_root / base_name
suffix = 1
while project_dir.exists():
    project_dir = projects_root / f"{base_name}_{suffix:02d}"
    suffix += 1
project_dir.mkdir(parents=True, exist_ok=True)
cmd = [
    "agent",
    "workflow",
    "run",
    request,
    "--team",
    team_name,
    "--workflow-type",
    workflow_type,
    "--test-command",
    test_command,
    "--project-dir",
    str(project_dir),
]
proc = subprocess.run(cmd, capture_output=True, text=True)
out = (proc.stdout or "") + ("\\n" + proc.stderr if proc.stderr else "")
print(out)
sys.exit(proc.returncode)
`;
      sendStatus("dev", "running", 35, "dev");
      const result = await captureAsync("docker", [
        "exec",
        "-i",
        CONTAINER,
        "python",
        "-c",
        py,
        request,
        teamName,
        workflowType,
        testCommand,
        taskId || workflowId
      ]);
      sendStatus("test", "running", 70, "test");

      const output = String(result.stdout || result.stderr || "");
      if (result.status !== 0) {
        sendJson({
          type: "workflow_result",
          messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          timestamp: Date.now(),
          payload: {
            taskId,
            workflowId,
            teamId,
            success: false,
            result: output || "workflow failed",
            tokensUsed: 0,
            duration: 0
          }
        });
        sendStatus("done", "failed", 100, "done");
        return;
      }

      const tokenMatch = output.match(/Total tokens:\s*([0-9]+)/i)
        || output.match(/总 Token 消耗[\s\S]*?([0-9]+)\s*tokens/i)
        || output.match(/tokens?\D+([0-9]+)/i);
      const tokensUsed = tokenMatch ? Number(tokenMatch[1]) : 0;
      sendJson({
        type: "workflow_result",
        messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
        payload: {
          taskId,
          workflowId,
          teamId,
          success: true,
          result: output,
          tokensUsed,
          duration: 0
        }
      });
      sendStatus("done", "completed", 100, "done");
    } catch (error) {
      sendJson({
        type: "workflow_result",
        messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
        payload: {
          taskId,
          workflowId,
          teamId,
          success: false,
          result: String(error?.message || error),
          tokensUsed: 0,
          duration: 0
        }
      });
      sendStatus("done", "failed", 100, "done");
    }
  };

  const syncTeamsToServer = async () => {
    try {
      const teams = getLocalTeamsForSync();
      await requestJson(
        `${server}/api/sync/teams`,
        "POST",
        { teams },
        { Authorization: `Bearer ${token}` }
      );
    } catch {
      // ignore transient sync failure
    }
  };

  const createLocalTeamIfNeeded = (teamName, description, teamType = "software_dev") => {
    ensureContainerStarted();
    const py = `
import json
import sys
from pathlib import Path
from anaagent.environment import create_environment
from anaagent.config_manager import get_base_config, normalize_team_type, update_team_claude_config_for_team

name = sys.argv[1].strip()
description = sys.argv[2]
raw_tt = sys.argv[3].strip() if len(sys.argv) > 3 else "software_dev"
canonical_tt = normalize_team_type(raw_tt)
if not name:
    print(json.dumps({"ok": False, "reason": "empty_name"}))
    sys.exit(0)

team_dir = Path('/root/.anaagent/environments') / name
# 目录已存在时旧逻辑会直接跳过，导致 team.yaml 仍是 software_dev（小程序常见：先占位再同步）
if team_dir.exists():
    upd = update_team_claude_config_for_team(name, team_type=canonical_tt)
    print(json.dumps({
        "ok": bool(upd.success),
        "created": False,
        "name": name,
        "team_type": canonical_tt,
        "type_align_msg": upd.message or "",
    }))
    sys.exit(0)

base = get_base_config() or {}
result = create_environment(
    name=name,
    description=description,
    auth_token=str(base.get("anthropic_auth_token", "") or ""),
    base_url=str(base.get("anthropic_base_url", "") or ""),
    model=str(base.get("anthropic_model", "") or ""),
    team_type=canonical_tt,
)
if result.success:
    print(json.dumps({"ok": True, "created": True, "name": name, "team_type": canonical_tt}))
else:
    print(json.dumps({"ok": False, "created": False, "name": name, "reason": result.message or "create_failed"}))
`;
    const typeArg = String(teamType || "software_dev").trim();
    const out = capture("docker", ["exec", "-i", CONTAINER, "python", "-c", py, teamName, description || "", typeArg]);
    if (out.status !== 0) {
      return { ok: false, created: false, name: teamName, reason: out.stderr || out.stdout || "docker_exec_failed" };
    }
    try {
      return JSON.parse(out.stdout || "{}");
    } catch {
      return { ok: false, created: false, name: teamName, reason: out.stdout || "invalid_json" };
    }
  };

  const deleteLocalTeamIfNeeded = (teamName) => {
    ensureContainerStarted();
    const raw = String(teamName || "").trim();
    if (!raw) {
      return { ok: false, name: "", reason: "empty_name" };
    }
    const py = `
import json
import sys
from anaagent.environment import remove_environment

name = sys.argv[1].strip()
if not name:
    print(json.dumps({"ok": False, "reason": "empty_name"}))
    sys.exit(0)
result = remove_environment(name)
print(json.dumps({
    "ok": bool(result.success),
    "name": name,
    "reason": str(result.message or "")
}))
`;
    const out = capture("docker", ["exec", "-i", CONTAINER, "python", "-c", py, raw]);
    if (out.status !== 0) {
      return { ok: false, name: raw, reason: out.stderr || out.stdout || "docker_exec_failed" };
    }
    try {
      return JSON.parse(out.stdout || "{}");
    } catch {
      return { ok: false, name: raw, reason: out.stdout || "invalid_json" };
    }
  };

  const syncPendingTeamsToLocal = async () => {
    try {
      await syncSettingsToDocker();
      const result = await requestJson(
        `${server}/api/sync/pending`,
        "GET",
        null,
        { Authorization: `Bearer ${token}` }
      );
      const pending = Array.isArray(result?.data) ? result.data : [];
      if (!pending.length) return;

      for (const item of pending) {
        const name = String(item?.name || "").trim();
        if (!name) continue;
        const description = String(item?.description || "");
        const pendingTeamType = pickPendingTeamType(item);
        const createRes = createLocalTeamIfNeeded(name, description, pendingTeamType);
        const teamId = `team_${name}`;
        sendJson({
          type: "team_created",
          messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          timestamp: Date.now(),
          payload: {
            teamId,
            teamName: name,
            success: Boolean(createRes?.ok)
          }
        });
      }
      await syncTeamsToServer();
    } catch {
      // ignore transient pull/create failure
    }
  };

  const connect = () => {
    ws = new WebSocketClass(wsUrl);

    ws.onopen = () => {
      sendJson({
        type: "auth",
        messageId: `msg_${Date.now()}`,
        timestamp: Date.now(),
        payload: { userId, token }
      });

      heartbeat = setInterval(() => {
        sendJson({
          type: "heartbeat",
          messageId: `msg_${Date.now()}`,
          timestamp: Date.now(),
          payload: {}
        });
      }, heartbeatIntervalMs);
      void syncSettingsToDocker();
      settingsSyncTimer = setInterval(() => {
        void syncSettingsToDocker();
      }, settingsSyncIntervalMs);
      void syncTeamsToServer();
      teamsSyncTimer = setInterval(() => {
        void syncTeamsToServer();
      }, teamsSyncIntervalMs);
      void syncPendingTeamsToLocal();
      pendingTeamsSyncTimer = setInterval(() => {
        void syncPendingTeamsToLocal();
      }, pendingTeamsSyncIntervalMs);
    };

    ws.onmessage = (event) => {
      let message = null;
      try {
        message = JSON.parse(String(event.data || "{}"));
      } catch {
        return;
      }
      if (message?.type === "workflow_run") {
        void handleWorkflowRun(message.payload || {});
      }
      if (message?.type === "create_team") {
        void syncPendingTeamsToLocal();
      }
      if (message?.type === "team_config_update") {
        try {
          applyTeamConfigToDocker(message.payload || {});
        } catch (e) {
          console.warn("team_config_update failed:", e?.message || e);
        }
      }
      if (message?.type === "request_delete_team") {
        const pl = message.payload || {};
        const teamName = String(pl.teamName || "").trim();
        const teamId = String(pl.teamId || (teamName ? `team_${teamName}` : "")).trim();
        if (!teamName) {
          return;
        }
        void (async () => {
          deleteLocalTeamIfNeeded(teamName);
          try {
            await syncTeamsToServer();
          } catch {
            // ignore
          }
          sendJson({
            type: "delete_team",
            messageId: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            timestamp: Date.now(),
            payload: {
              teamId,
              teamName
            }
          });
        })();
      }
    };

    ws.onerror = () => {
      // ignore details; reconnect on close
    };

    ws.onclose = () => {
      if (heartbeat) {
        clearInterval(heartbeat);
        heartbeat = null;
      }
      if (settingsSyncTimer) {
        clearInterval(settingsSyncTimer);
        settingsSyncTimer = null;
      }
      if (teamsSyncTimer) {
        clearInterval(teamsSyncTimer);
        teamsSyncTimer = null;
      }
      if (pendingTeamsSyncTimer) {
        clearInterval(pendingTeamsSyncTimer);
        pendingTeamsSyncTimer = null;
      }
      setTimeout(connect, 3000);
    };
  };

  connect();

  process.on("SIGTERM", () => {
    if (heartbeat) clearInterval(heartbeat);
    if (settingsSyncTimer) clearInterval(settingsSyncTimer);
    if (teamsSyncTimer) clearInterval(teamsSyncTimer);
    if (pendingTeamsSyncTimer) clearInterval(pendingTeamsSyncTimer);
    if (ws && ws.readyState === WebSocketClass.OPEN) ws.close();
    process.exit(0);
  });
}

function applyTeamConfigToDocker(payload) {
  const teamName = String(payload?.teamName || "").trim();
  if (!teamName) return;
  ensureContainerStarted();
  const ttRaw =
    payload?.teamType ??
    payload?.team_type ??
    "";
  const cfg = {
    name: teamName,
    anthropicAuthToken: payload?.anthropicAuthToken ?? "",
    anthropicBaseUrl: payload?.anthropicBaseUrl ?? "",
    anthropicModel: payload?.anthropicModel ?? "",
    teamType: ttRaw,
    team_type: ttRaw
  };
  const py = `
import json
import sys
from anaagent.config_manager import update_team_claude_config_for_team
raw = sys.argv[1]
cfg = json.loads(raw)
name = str(cfg.get("name") or "").strip()
token = cfg.get("anthropicAuthToken")
url = cfg.get("anthropicBaseUrl")
model = cfg.get("anthropicModel")
tt = str(cfg.get("teamType") or cfg.get("team_type") or "").strip()
if not name:
    print(json.dumps({"success": False, "reason": "empty_name"}))
else:
    r = update_team_claude_config_for_team(
        name,
        auth_token=token if token is not None else None,
        base_url=url if url is not None else None,
        model=model if model is not None else None,
        team_type=tt if tt else None,
    )
    print(json.dumps({"success": bool(r.success), "message": getattr(r, "message", "")}))
`;
  capture("docker", ["exec", "-i", CONTAINER, "python", "-c", py, JSON.stringify(cfg)]);
}

function applySettingsToDocker(anthropicAuthToken, anthropicBaseUrl, anthropicModel) {
  const script = `
import json
from pathlib import Path

token = ${JSON.stringify(anthropicAuthToken)}
base_url = ${JSON.stringify(anthropicBaseUrl)}
model = ${JSON.stringify(anthropicModel)}

root = Path('/root/.anaagent')
root.mkdir(parents=True, exist_ok=True)

base_cfg_path = root / 'base_config.json'
base_cfg = {}
if base_cfg_path.exists():
    try:
        base_cfg = json.loads(base_cfg_path.read_text(encoding='utf-8') or '{}')
    except Exception:
        base_cfg = {}
base_cfg['anthropic_auth_token'] = token
base_cfg['anthropic_base_url'] = base_url
base_cfg['anthropic_model'] = model
base_cfg_path.write_text(json.dumps(base_cfg, ensure_ascii=False, indent=2), encoding='utf-8')
`;

  capture("docker", ["exec", "-i", CONTAINER, "python", "-c", script]);
}

main().catch((error) => {
  console.error(`ERROR ${error.message || error}`);
  process.exit(1);
});

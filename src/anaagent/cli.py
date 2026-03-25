"""CLI入口 - 使用Typer框架

命令设计参考 conda 风格：
- agent create <name>         创建团队
- agent activate <name>       激活团队
- agent deactivate            退出团队
- agent list                  列出团队
- agent remove <name>         删除团队
- agent info                  查看当前团队信息
- agent install skill/xxx     安装组件
"""

import os
import typer
from rich.console import Console
from rich.table import Table

from anaagent import __version__

app = typer.Typer(
    name="agent",
    help="Agent Team Management - Like conda for AI Agent teams",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ============================================
# 核心命令（仿conda风格）
# ============================================

@app.command()
def create(
    name: str = typer.Argument(..., help="Team name"),
    description: str = typer.Option("", "-d", "--description", help="Team description"),
):
    """Create a new agent team (like: conda create -n name)"""
    from anaagent.environment import create_environment
    from anaagent.config_manager import get_base_config, mask_token

    # 获取base默认配置
    base_config = get_base_config()

    console.print(f"\n[bold cyan]Creating team: {name}[/bold cyan]")
    console.print("[dim]Press Enter to use default value[/dim]\n")

    # 交互式输入 API Token
    default_token = base_config.get("anthropic_auth_token", "")
    default_token_hint = mask_token(default_token) if default_token else "(not set)"
    token = typer.prompt(
        f"ANTHROPIC_AUTH_TOKEN (apiKey)",
        default="",
        show_default=False,
        prompt_suffix=f" [{default_token_hint}]: "
    )
    if not token:
        token = default_token

    # 交互式输入 Base URL
    default_url = base_config.get("anthropic_base_url", "https://api.anthropic.com")
    url = typer.prompt(
        f"ANTHROPIC_BASE_URL (baseUrl)",
        default="",
        show_default=False,
        prompt_suffix=f" [{default_url}]: "
    )
    if not url:
        url = default_url

    # 交互式输入 Model
    default_model = base_config.get("anthropic_model", "claude-sonnet-4-6")
    model = typer.prompt(
        f"ANTHROPIC_MODEL (modelName)",
        default="",
        show_default=False,
        prompt_suffix=f" [{default_model}]: "
    )
    if not model:
        model = default_model

    # 创建团队
    result = create_environment(name, description, token, url, model)
    if result.success:
        console.print(f"\n[green]OK[/green] Team '{name}' created")
        console.print(f"  Path: {result.path}")
        console.print(f"  Model: {model}")
        console.print(f"\n  To activate: [cyan]agent activate {name}[/cyan]")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@app.command()
def activate(
    name: str = typer.Argument(..., help="Team name to activate"),
):
    """Activate a team and start shell with prompt (like: conda activate name)"""
    import subprocess
    from anaagent.environment import activate_environment, _get_team_path, ENVS_DIR

    team_path = _get_team_path(name)

    if not team_path.exists():
        console.print(f"[red]ERROR[/red] Team '{name}' not found")
        console.print(f"Create it with: [cyan]agent create {name}[/cyan]")
        return

    # 激活团队（更新内部状态）
    result = activate_environment(name)
    if not result.success:
        console.print(f"[red]ERROR[/red] {result.message}")
        return

    # 设置环境变量
    env = os.environ.copy()
    env["AGENT_ACTIVE_TEAM"] = name
    env["ANAAGENT_ENV"] = str(team_path)

    # 启动新的 bash shell，带有自定义提示符
    bashrc_content = f'''
# Source system bashrc
if [ -f /etc/bash.bashrc ]; then source /etc/bash.bashrc; fi
if [ -f ~/.bashrc ]; then source ~/.bashrc; fi

# Set prompt with team name
export PS1="({name}) \\u@\\h:\\w\\$ "

# Function to detect deactivate and exit shell
_check_deactivate() {{
    if [ $? -eq 42 ]; then
        exit 0
    fi
}}
trap _check_deactivate DEBUG

# Welcome message
echo ""
echo "  Team: {name}"
echo "  Path: {team_path}"
echo "  Type 'exit' or 'agent deactivate' to return to base"
echo ""
'''

    # 写入临时 bashrc
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bashrc', delete=False) as f:
        f.write(bashrc_content)
        temp_bashrc = f.name

    try:
        # 启动 bash
        subprocess.run(['/bin/bash', '--rcfile', temp_bashrc], env=env)
    finally:
        os.unlink(temp_bashrc)


@app.command()
def deactivate():
    """Deactivate current team and return to base shell (like: conda deactivate)"""
    from anaagent.environment import deactivate_environment

    result = deactivate_environment()
    if result.success:
        console.print("[green]OK[/green] Returning to base environment...")
        # 返回特殊退出码 42，shell 会检测并退出
        import sys
        sys.exit(42)
    else:
        console.print(f"[yellow]{result.message}[/yellow]")
        console.print("Already in base environment. Type 'exit' to leave container.")


@app.command("list")
def list_teams():
    """List all teams (like: conda env list)"""
    from anaagent.environment import list_environments

    envs = list_environments()
    if not envs:
        console.print("[yellow]No teams found[/yellow]")
        console.print("\n  Create one: [cyan]agent create <name>[/cyan]")
        return

    table = Table(title="Agent Teams")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")
    table.add_column("Description", style="dim")

    for env in envs:
        status = "[green]* active[/green]" if env.active else "  inactive"
        table.add_row(env.name, status, env.created_at, env.description or "-")

    console.print(table)


@app.command()
def remove(
    name: str = typer.Argument(..., help="Team name to remove"),
    force: bool = typer.Option(False, "-f", "--force", help="Force removal"),
):
    """Remove a team (like: conda remove -n name)"""
    from anaagent.environment import remove_environment

    if not force:
        confirm = typer.confirm(f"Remove team '{name}'?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    result = remove_environment(name)
    if result.success:
        console.print(f"[green]OK[/green] Team '{name}' removed")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@app.command()
def info():
    """Show current team info (like: conda info)"""
    from anaagent.environment import get_current_environment
    from anaagent.team_io import get_team_info

    env_path = get_current_environment()
    if not env_path:
        console.print("[yellow]No active team[/yellow]")
        console.print("\n  Activate one: [cyan]agent activate <name>[/cyan]")
        return

    team_name = env_path.name
    info_data = get_team_info(team_name)

    console.print(f"\n[bold cyan]Active Team: {team_name}[/bold cyan]")
    console.print(f"  Path: {env_path}")
    console.print(f"  Description: {info_data.get('description', '-')}")
    console.print(f"  Default Model: {info_data.get('default_model', '-')}")

    console.print(f"\n  [bold]Components:[/bold]")
    console.print(f"    Agents: {info_data.get('agent_count', 0)}")
    console.print(f"    Skills: {info_data.get('skill_count', 0)}")
    console.print(f"    Hooks: {info_data.get('hook_count', 0)}")
    console.print(f"    MCPs: {info_data.get('mcp_count', 0)}")


@app.command()
def clone(
    source: str = typer.Argument(..., help="Source team name"),
    new_name: str = typer.Argument(..., help="New team name"),
):
    """Clone a team"""
    from anaagent.team_io import clone_team

    result = clone_team(source, new_name)
    if result.success:
        console.print(f"[green]OK[/green] Cloned '{source}' to '{new_name}'")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


# ============================================
# Agent成员管理（子命令）
# ============================================
member_app = typer.Typer(help="Team member management")
app.add_typer(member_app, name="member")


@member_app.command("add")
def member_add(
    name: str = typer.Argument(..., help="Member name"),
    role: str = typer.Option("developer", "-r", "--role", help="Role"),
    model: str = typer.Option(None, "-m", "--model", help="Model"),
    skills: str = typer.Option(None, "-s", "--skills", help="Skills (comma-separated)"),
):
    """Add a team member"""
    from anaagent.agent_manager import add_agent
    from anaagent.config_manager import load_config, mask_token
    import yaml

    # 获取团队配置作为默认值
    team_config = load_config()
    team_token = ""
    team_url = ""
    team_model = ""

    if team_config:
        # 从团队的.claude/settings.json读取配置
        from anaagent.environment import get_current_environment
        env_path = get_current_environment()
        if env_path:
            settings_path = env_path / ".claude" / "settings.json"
            if settings_path.exists():
                try:
                    import json
                    with open(settings_path, encoding="utf-8") as f:
                        settings = json.load(f)
                    env = settings.get("env", {})
                    team_token = env.get("ANTHROPIC_AUTH_TOKEN", "")
                    team_url = env.get("ANTHROPIC_BASE_URL", "")
                    team_model = env.get("ANTHROPIC_MODEL", "")
                except Exception:
                    pass

    console.print(f"\n[bold cyan]Adding member: {name}[/bold cyan]")
    console.print("[dim]Press Enter to use team's default value[/dim]\n")

    # 交互式输入 API Token
    default_token_hint = mask_token(team_token) if team_token else "(team default)"
    token = typer.prompt(
        f"ANTHROPIC_AUTH_TOKEN (apiKey)",
        default="",
        show_default=False,
        prompt_suffix=f" [{default_token_hint}]: "
    )
    if not token:
        token = team_token

    # 交互式输入 Base URL
    url = typer.prompt(
        f"ANTHROPIC_BASE_URL (baseUrl)",
        default="",
        show_default=False,
        prompt_suffix=f" [{team_url or '(not set)'}]: "
    )
    if not url:
        url = team_url

    # 交互式输入 Model
    model_default = model or team_model or "claude-sonnet-4-6"
    input_model = typer.prompt(
        f"ANTHROPIC_MODEL (modelName)",
        default="",
        show_default=False,
        prompt_suffix=f" [{model_default}]: "
    )
    if input_model:
        model = input_model
    elif not model:
        model = model_default

    skill_list = [s.strip() for s in skills.split(",")] if skills else []
    result = add_agent(name, role, "", model, skill_list, token, url, model)

    if result.success:
        console.print(f"[green]OK[/green] Member '{name}' added")
        console.print(f"  Role: {role}")
        console.print(f"  Model: {model}")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@member_app.command("list")
def member_list():
    """List team members"""
    from anaagent.agent_manager import list_agents

    agents = list_agents()
    if not agents:
        console.print("[yellow]No members in current team[/yellow]")
        return

    table = Table(title="Team Members")
    table.add_column("Name", style="cyan")
    table.add_column("Role", style="green")
    table.add_column("Model", style="dim")
    table.add_column("Skills", style="dim")

    for agent in agents:
        model = agent.model or "(default)"
        skills = ", ".join(agent.skills) if agent.skills else "-"
        table.add_row(agent.name, agent.role, model, skills)

    console.print(table)


@member_app.command("remove")
def member_remove(
    name: str = typer.Argument(..., help="Member name"),
):
    """Remove a team member"""
    from anaagent.agent_manager import remove_agent

    result = remove_agent(name)
    if result.success:
        console.print(f"[green]OK[/green] Member '{name}' removed")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


# ============================================
# 安装命令
# ============================================
@app.command()
def install(
    component: str = typer.Argument(..., help="Component to install (skill/name, mcp/name, hook/name)"),
):
    """Install a component (like: conda install package)"""
    from anaagent.component_manager import install_skill, install_mcp, install_hook
    from anaagent.marketplace import install_from_market

    # 解析类型和名称
    if "/" in component:
        comp_type, comp_name = component.split("/", 1)
    else:
        # 默认尝试从市场安装
        result = install_from_market(component, "skill")
        if result.success:
            console.print(f"[green]OK[/green] '{component}' installed from market")
        else:
            console.print(f"[red]ERROR[/red] {result.message}")
        return

    if comp_type == "skill":
        result = install_skill(comp_name)
    elif comp_type == "mcp":
        result = install_mcp(comp_name)
    elif comp_type == "hook":
        result = install_hook(comp_name)
    else:
        console.print(f"[red]ERROR[/red] Unknown type: {comp_type}")
        return

    if result.success:
        console.print(f"[green]OK[/green] {comp_type}/{comp_name} installed")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


# ============================================
# 列出组件
# ============================================
@app.command("list-components")
def list_components(
    component_type: str = typer.Argument(None, help="Type: skills, mcps, hooks"),
):
    """List installed components"""
    from anaagent.component_manager import list_skills, list_mcps, list_hooks

    if component_type == "skills":
        items = list_skills()
        if not items:
            console.print("[yellow]No skills installed[/yellow]")
            return
        table = Table(title="Skills")
        for item in items:
            table.add_row(item["name"], item.get("description", "")[:40])
    elif component_type == "mcps":
        items = list_mcps()
        if not items:
            console.print("[yellow]No MCPs installed[/yellow]")
            return
        table = Table(title="MCP Services")
        for item in items:
            table.add_row(item["name"], item.get("status", ""))
    elif component_type == "hooks":
        items = list_hooks()
        if not items:
            console.print("[yellow]No hooks installed[/yellow]")
            return
        table = Table(title="Hooks")
        for item in items:
            table.add_row(item["name"], item.get("type", ""))
    else:
        # 列出所有
        console.print("\n[bold]Skills:[/bold]")
        for s in list_skills():
            console.print(f"  - {s['name']}")
        console.print("\n[bold]MCPs:[/bold]")
        for m in list_mcps():
            console.print(f"  - {m['name']}")
        console.print("\n[bold]Hooks:[/bold]")
        for h in list_hooks():
            console.print(f"  - {h['name']}")
        return

    console.print(table)


# ============================================
# 市场命令
# ============================================
market_app = typer.Typer(help="Marketplace")
app.add_typer(market_app, name="market")


@market_app.command("list")
def market_list():
    """List marketplace items"""
    from anaagent.marketplace import list_market

    items = list_market()
    table = Table(title="Marketplace")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description", style="dim")

    for item in items:
        table.add_row(item["name"], item["type"], item.get("description", "")[:40])

    console.print(table)


@market_app.command("search")
def market_search(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search marketplace"""
    from anaagent.marketplace import search_market

    items = search_market(query)
    if not items:
        console.print("[yellow]No results[/yellow]")
        return

    table = Table(title=f"Results for '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")

    for item in items:
        table.add_row(item["name"], item["type"])

    console.print(table)


@market_app.command("install")
def market_install(
    type: str = typer.Argument(..., help="Type: skill, agent, hook"),
    name: str = typer.Argument(..., help="Item name"),
):
    """Install from marketplace"""
    from anaagent.marketplace import install_from_market

    result = install_from_market(name, type)
    if result.success:
        console.print(f"[green]OK[/green] {type}/{name} installed")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


# ============================================
# 配置命令
# ============================================
config_app = typer.Typer(help="Configuration")
app.add_typer(config_app, name="config")


@config_app.command("set-base")
def config_set_base():
    """Set base environment default configuration"""
    from anaagent.config_manager import set_base_config, get_base_config, mask_token

    current = get_base_config()

    console.print("\n[bold cyan]Configure Base Environment Defaults[/bold cyan]")
    console.print("[dim]These will be used as defaults when creating teams[/dim]\n")

    # 输入 API Token
    current_token = current.get("anthropic_auth_token", "")
    hint = mask_token(current_token) if current_token else "(not set)"
    token = typer.prompt(
        "ANTHROPIC_AUTH_TOKEN (apiKey)",
        default="",
        show_default=False,
        prompt_suffix=f" [{hint}]: "
    )
    if not token and current_token:
        token = current_token

    # 输入 Base URL
    current_url = current.get("anthropic_base_url", "https://api.anthropic.com")
    url = typer.prompt(
        "ANTHROPIC_BASE_URL (baseUrl)",
        default="",
        show_default=False,
        prompt_suffix=f" [{current_url}]: "
    )
    if not url:
        url = current_url

    # 输入 Model
    current_model = current.get("anthropic_model", "claude-sonnet-4-6")
    model = typer.prompt(
        "ANTHROPIC_MODEL (modelName)",
        default="",
        show_default=False,
        prompt_suffix=f" [{current_model}]: "
    )
    if not model:
        model = current_model

    result = set_base_config(token, url, model)
    if result.success:
        console.print(f"\n[green]OK[/green] Base environment configured")
        console.print(f"  Model: {model}")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@config_app.command("show-base")
def config_show_base():
    """Show base environment configuration"""
    from anaagent.config_manager import get_base_config, mask_token

    config = get_base_config()
    console.print("\n[bold cyan]Base Environment Configuration[/bold cyan]")
    console.print(f"  ANTHROPIC_AUTH_TOKEN: {mask_token(config.get('anthropic_auth_token', ''))}")
    console.print(f"  ANTHROPIC_BASE_URL: {config.get('anthropic_base_url', '-')}")
    console.print(f"  ANTHROPIC_MODEL: {config.get('anthropic_model', '-')}")


@config_app.command("set-team")
def config_set_team():
    """Set current team's Claude configuration"""
    import yaml
    from anaagent.environment import get_current_environment
    from anaagent.config_manager import mask_token, update_team_claude_config

    env_path = get_current_environment()
    if not env_path:
        console.print("[red]ERROR[/red] No active team. Run 'agent activate <name>' first.")
        return

    team_name = env_path.name
    team_yaml_path = env_path / "team.yaml"

    # 从team.yaml读取当前配置
    current = {}
    if team_yaml_path.exists():
        try:
            with open(team_yaml_path, encoding="utf-8") as f:
                current = yaml.safe_load(f) or {}
        except Exception:
            pass

    console.print(f"\n[bold cyan]Configure Team: {team_name}[/bold cyan]")
    console.print("[dim]Press Enter to keep current value[/dim]\n")

    # 输入 API Token
    current_token = current.get("anthropic_auth_token", "")
    hint = mask_token(current_token) if current_token else "(not set)"
    token = typer.prompt(
        "ANTHROPIC_AUTH_TOKEN (apiKey)",
        default="",
        show_default=False,
        prompt_suffix=f" [{hint}]: "
    )
    if not token and current_token:
        token = current_token

    # 输入 Base URL
    current_url = current.get("anthropic_base_url", "https://api.anthropic.com")
    url = typer.prompt(
        "ANTHROPIC_BASE_URL (baseUrl)",
        default="",
        show_default=False,
        prompt_suffix=f" [{current_url}]: "
    )
    if not url:
        url = current_url

    # 输入 Model
    current_model = current.get("anthropic_model", "claude-sonnet-4-6")
    model = typer.prompt(
        "ANTHROPIC_MODEL (modelName)",
        default="",
        show_default=False,
        prompt_suffix=f" [{current_model}]: "
    )
    if not model:
        model = current_model

    # 保存配置（同时更新team.yaml和.claude/settings.json）
    result = update_team_claude_config(token, url, model)
    if result.success:
        console.print(f"\n[green]OK[/green] Team '{team_name}' configured")
        console.print(f"  Model: {model}")
        console.print(f"  Config saved to: {team_yaml_path}")
        console.print(f"\n  [yellow]Run [cyan]agent refresh[/cyan] to update environment variables[/yellow]")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@config_app.command("show-team")
def config_show_team():
    """Show current team's Claude configuration"""
    import yaml
    from anaagent.environment import get_current_environment
    from anaagent.config_manager import mask_token
    from anaagent.agent_manager import list_agents

    env_path = get_current_environment()
    if not env_path:
        console.print("[red]ERROR[/red] No active team. Run 'agent activate <name>' first.")
        return

    team_name = env_path.name
    team_yaml_path = env_path / "team.yaml"

    # 从team.yaml读取配置
    config = {}
    if team_yaml_path.exists():
        try:
            with open(team_yaml_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    # 统计团队成员
    agents = list_agents()
    agent_count = len(agents)

    # 统计其他组件
    skills_path = env_path / "skills"
    mcps_path = env_path / "mcps"
    hooks_path = env_path / "hooks"

    skill_count = len(list(skills_path.iterdir())) if skills_path.exists() else 0
    mcp_count = len(list(mcps_path.iterdir())) if mcps_path.exists() else 0
    hook_count = len([f for f in hooks_path.glob("*.py")]) if hooks_path.exists() else 0

    console.print(f"\n[bold cyan]Team: {team_name}[/bold cyan]")
    console.print(f"  Description: {config.get('description', '-')}")
    console.print(f"  Created: {config.get('created_at', '-')}")

    console.print(f"\n[bold]Claude Configuration:[/bold]")
    console.print(f"  ANTHROPIC_AUTH_TOKEN: {mask_token(config.get('anthropic_auth_token', ''))}")
    console.print(f"  ANTHROPIC_BASE_URL: {config.get('anthropic_base_url', '-')}")
    console.print(f"  ANTHROPIC_MODEL: {config.get('anthropic_model', '-')}")

    console.print(f"\n[bold]Team Components:[/bold]")
    console.print(f"  Members: {agent_count}")
    console.print(f"  Skills: {skill_count}")
    console.print(f"  MCPs: {mcp_count}")
    console.print(f"  Hooks: {hook_count}")

    if agents:
        console.print(f"\n[bold]Team Members:[/bold]")
        for agent in agents[:5]:
            console.print(f"  - {agent.name} ({agent.role})")


@config_app.command("set-key")
def config_set_key(
    provider: str = typer.Argument(..., help="Provider name"),
    key: str = typer.Argument(..., help="API key"),
):
    """Set API key"""
    from anaagent.config_manager import set_api_key

    result = set_api_key(provider, key)
    if result.success:
        masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
        console.print(f"[green]OK[/green] {provider}: {masked}")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@config_app.command("keys")
def config_keys():
    """List API keys"""
    from anaagent.config_manager import list_api_keys

    keys = list_api_keys()
    if not keys:
        console.print("[yellow]No API keys configured[/yellow]")
        return

    for provider, masked in keys.items():
        console.print(f"  {provider}: {masked}")


@config_app.command("show")
def config_show():
    """Show configuration"""
    from anaagent.config_manager import load_config

    config = load_config()
    if not config:
        console.print("[yellow]No active team[/yellow]")
        return

    console.print(f"\n[bold]Team: {config.get('name', '-')}[/bold]")
    console.print(f"  Model: {config.get('default_model', '-')}")
    console.print(f"  Created: {config.get('created_at', '-')}")

    keys = config.get("api_keys", {})
    if keys:
        console.print(f"\n  [bold]API Keys:[/bold]")
        for p in keys:
            console.print(f"    - {p}: (configured)")


# ============================================
# 记忆命令
# ============================================
memory_app = typer.Typer(help="Memory management")
app.add_typer(memory_app, name="memory")


@memory_app.command("add")
def memory_add(
    content: str = typer.Argument(..., help="Memory content"),
    category: str = typer.Option("note", "-c", "--category", help="Category"),
):
    """Add a memory"""
    from anaagent.memory_manager import add_to_memory

    success = add_to_memory(content, category)
    if success:
        console.print(f"[green]OK[/green] Memory added")
    else:
        console.print("[red]ERROR[/red] Failed")


@memory_app.command("recall")
def memory_recall(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search memories"""
    from anaagent.memory_manager import recall_memory

    memories = recall_memory(query)
    if not memories:
        console.print("[yellow]No memories found[/yellow]")
        return

    for mem in memories[:5]:
        console.print(f"  - {mem['content'][:60]}...")


@memory_app.command("show")
def memory_show():
    """Show memory context"""
    from anaagent.memory_manager import get_memory_context

    context = get_memory_context()
    console.print(context)


# ============================================
# Token使用命令
# ============================================
usage_app = typer.Typer(help="Token usage")
app.add_typer(usage_app, name="usage")


@usage_app.command("today")
def usage_today():
    """Today's usage"""
    from anaagent.usage_monitor import get_daily_usage

    stats = get_daily_usage()
    console.print(f"\n  Tokens: {stats['total_tokens']:,}")
    console.print(f"  Cost: ${stats['total_cost']:.4f}")


@usage_app.command("stats")
def usage_stats():
    """Usage statistics"""
    from anaagent.usage_monitor import get_usage_by_agent

    stats = get_usage_by_agent()
    if not stats:
        console.print("[yellow]No usage data[/yellow]")
        return

    for agent, data in stats.items():
        console.print(f"  {agent}: {data['total_tokens']:,} tokens")


# ============================================
# 导入导出命令
# ============================================
@app.command()
def export(
    team: str = typer.Argument(..., help="Team name"),
):
    """Export team"""
    from anaagent.team_io import export_team

    result = export_team(team)
    if result.success:
        console.print(f"[green]OK[/green] Exported to: {result.path}")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@app.command()
def import_team(
    package: str = typer.Argument(..., help="Package file"),
    name: str = typer.Option(None, "-n", "--name", help="New team name"),
):
    """Import team"""
    from anaagent.team_io import import_team as do_import

    result = do_import(package, name)
    if result.success:
        console.print(f"[green]OK[/green] Team imported")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


# ============================================
# 版本命令
# ============================================
@app.command()
def version():
    """Show version"""
    console.print(f"[bold cyan]agent[/bold cyan] version {__version__}")


# ============================================
# 兼容旧命令（保持向后兼容）
# ============================================
# 创建别名
env_app = typer.Typer(help="Environment (deprecated, use top-level commands)")
app.add_typer(env_app, name="env")


@env_app.command("create")
def env_create(
    name: str = typer.Option(..., "-n", "--name", help="Team name"),
    description: str = typer.Option("", "-d", "--description", help="Team description"),
):
    """Create environment (deprecated)"""
    from anaagent.environment import create_environment
    result = create_environment(name, description)
    if result.success:
        console.print(f"[green]OK[/green] Team '{name}' created")
    else:
        console.print(f"[red]ERROR[/red] {result.message}")


@env_app.command("list")
def env_list():
    """List environments (deprecated)"""
    list_teams()


@env_app.command("activate")
def env_activate(
    name: str = typer.Argument(..., help="Team name"),
):
    """Activate environment (deprecated)"""
    activate(name)


@env_app.command("deactivate")
def env_deactivate():
    """Deactivate environment (deprecated)"""
    deactivate()


@env_app.command("remove")
def env_remove(
    name: str = typer.Argument(..., help="Team name"),
    force: bool = typer.Option(False, "-f", "--force"),
):
    """Remove environment (deprecated)"""
    remove(name, force)


if __name__ == "__main__":
    app()
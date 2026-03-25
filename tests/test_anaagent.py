"""Anaagent 单元测试"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# 设置测试环境
os.environ["HOME"] = str(Path.home())


class TestEnvironment:
    """环境管理测试"""

    def setup_method(self):
        """每个测试前清理"""
        self.test_env = "test_env_unit"

    def teardown_method(self):
        """每个测试后清理"""
        from anaagent.environment import remove_environment
        try:
            remove_environment(self.test_env)
        except:
            pass

    def test_create_environment(self):
        """测试创建环境"""
        from anaagent.environment import create_environment

        result = create_environment(self.test_env, "Test environment")
        assert result.success, f"Failed: {result.message}"
        assert result.path.exists()

    def test_create_duplicate_environment(self):
        """测试创建重复环境"""
        from anaagent.environment import create_environment

        create_environment(self.test_env)
        result = create_environment(self.test_env)
        assert not result.success
        # 中文或英文都接受
        assert "exists" in result.message.lower() or "存在" in result.message

    def test_list_environments(self):
        from anaagent.environment import create_environment, list_environments

        create_environment(self.test_env)
        envs = list_environments()
        names = [e.name for e in envs]
        assert self.test_env in names

    def test_activate_environment(self):
        from anaagent.environment import create_environment, activate_environment

        create_environment(self.test_env)
        result = activate_environment(self.test_env)
        assert result.success

    def test_remove_environment(self):
        from anaagent.environment import create_environment, remove_environment

        create_environment(self.test_env)
        result = remove_environment(self.test_env)
        assert result.success


class TestAgentManager:
    """Agent管理测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_agent_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_add_agent(self):
        from anaagent.agent_manager import add_agent

        result = add_agent("test_agent", "developer", "Test agent")
        assert result.success

    def test_add_duplicate_agent(self):
        from anaagent.agent_manager import add_agent

        add_agent("test_agent")
        result = add_agent("test_agent")
        assert not result.success

    def test_list_agents(self):
        from anaagent.agent_manager import add_agent, list_agents

        add_agent("agent1", "developer")
        add_agent("agent2", "reviewer")

        agents = list_agents()
        assert len(agents) == 2
        names = [a.name for a in agents]
        assert "agent1" in names
        assert "agent2" in names

    def test_remove_agent(self):
        from anaagent.agent_manager import add_agent, remove_agent

        add_agent("test_agent")
        result = remove_agent("test_agent")
        assert result.success


class TestComponentManager:
    """组件管理测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_component_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_install_skill(self):
        from anaagent.component_manager import install_skill, list_skills

        result = install_skill("test-skill")
        assert result.success

        skills = list_skills()
        names = [s["name"] for s in skills]
        assert "test-skill" in names

    def test_install_mcp(self):
        from anaagent.component_manager import install_mcp, list_mcps

        result = install_mcp("test-mcp")
        assert result.success

        mcps = list_mcps()
        names = [m["name"] for m in mcps]
        assert "test-mcp" in names

    def test_install_hook(self):
        from anaagent.component_manager import install_hook, list_hooks

        result = install_hook("test-hook.py")
        assert result.success

        hooks = list_hooks()
        names = [h["name"] for h in hooks]
        assert "test-hook.py" in names


class TestConfigManager:
    """配置管理测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_config_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_set_api_key(self):
        from anaagent.config_manager import set_api_key, get_api_key

        set_api_key("test-provider", "test-key-123")
        key = get_api_key("test-provider")
        assert key == "test-key-123"

    def test_list_api_keys(self):
        from anaagent.config_manager import set_api_key, list_api_keys

        set_api_key("provider1", "key1")
        set_api_key("provider2", "key2")

        keys = list_api_keys()
        assert "provider1" in keys
        assert "provider2" in keys

    def test_set_setting(self):
        from anaagent.config_manager import set_setting, get_setting

        set_setting("test_key", "test_value")
        value = get_setting("test_key")
        assert value == "test_value"


class TestMemoryManager:
    """记忆管理测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_memory_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_add_memory(self):
        from anaagent.memory_manager import add_to_memory, recall_memory

        add_to_memory("Test memory content", "note", 0.5)

        results = recall_memory("Test")
        assert len(results) > 0
        assert "Test memory content" in results[0]["content"]

    def test_memory_categories(self):
        from anaagent.memory_manager import add_to_memory, recall_memory

        add_to_memory("Decision 1", "decision", 0.9)
        add_to_memory("Preference 1", "preference", 0.7)
        add_to_memory("Note 1", "note", 0.5)

        # 验证都添加成功
        results = recall_memory("1")
        assert len(results) == 3


class TestCommandsManager:
    """命令管理测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_cmd_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_create_command(self):
        from anaagent.commands_manager import create_command, get_command

        create_command(
            "test-command",
            "Test command description",
            "Content for $ARGUMENTS"
        )

        cmd = get_command("test-command")
        assert cmd is not None
        assert cmd.description == "Test command description"

    def test_list_commands(self):
        from anaagent.commands_manager import create_command, list_commands

        create_command("cmd1", "Command 1")
        create_command("cmd2", "Command 2")

        commands = list_commands()
        names = [c.name for c in commands]
        assert "cmd1" in names
        assert "cmd2" in names

    def test_render_command(self):
        from anaagent.commands_manager import create_command, get_command, render_command_prompt

        create_command("greet", "Greeting command", "Hello, $ARGUMENTS!")

        cmd = get_command("greet")
        prompt = render_command_prompt(cmd, "World")
        assert prompt == "Hello, World!"


class TestClaudeIntegration:
    """Claude集成测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_claude_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_generate_claude_md(self):
        from anaagent.claude_integration import generate_claude_md

        result = generate_claude_md()
        assert result.success
        assert result.path.exists()
        assert result.path.name == "CLAUDE.md"

    def test_claude_md_content(self):
        from anaagent.claude_integration import generate_claude_md

        result = generate_claude_md()
        assert result.success
        content = result.path.read_text(encoding="utf-8")

        # 应包含团队信息
        assert self.test_env in content or "Team" in content


class TestMarketplace:
    """市场测试"""

    def test_list_market(self):
        from anaagent.marketplace import list_market

        items = list_market()
        assert len(items) > 0

    def test_search_market(self):
        from anaagent.marketplace import search_market

        results = search_market("python")
        assert len(results) > 0
        assert any("python" in r["name"].lower() or "python" in r.get("description", "").lower() for r in results)


class TestUsageMonitor:
    """使用监控测试"""

    def setup_method(self):
        from anaagent.environment import create_environment, activate_environment
        self.test_env = "test_usage_env"
        create_environment(self.test_env)
        activate_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import deactivate_environment, remove_environment
        deactivate_environment()
        remove_environment(self.test_env)

    def test_record_usage(self):
        from anaagent.usage_monitor import record_usage, get_daily_usage

        record_usage("test_agent", "claude-sonnet-4-6", 1000, 500)

        stats = get_daily_usage()
        assert stats["total_tokens"] == 1500
        assert stats["total_input_tokens"] == 1000
        assert stats["total_output_tokens"] == 500

    def test_calculate_cost(self):
        from anaagent.usage_monitor import calculate_cost

        # 测试 sonnet 价格
        cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        # 输入: $0.003/1M, 输出: $0.015/1M
        assert cost == 0.018


class TestTeamIO:
    """团队导入导出测试"""

    def setup_method(self):
        from anaagent.environment import create_environment
        self.test_env = "test_io_env"
        create_environment(self.test_env)

    def teardown_method(self):
        from anaagent.environment import remove_environment
        try:
            remove_environment(self.test_env)
        except:
            pass
        try:
            remove_environment(f"{self.test_env}_cloned")
        except:
            pass
        # 清理导出文件
        for f in Path(".").glob("*.anaagent"):
            f.unlink()

    def test_export_team(self):
        from anaagent.team_io import export_team

        result = export_team(self.test_env)
        assert result.success
        assert result.path.exists()
        assert result.path.suffix == ".anaagent"

    def test_clone_team(self):
        from anaagent.team_io import clone_team

        result = clone_team(self.test_env, f"{self.test_env}_cloned")
        assert result.success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
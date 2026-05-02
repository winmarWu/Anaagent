"""文章撰写 / 科研辅助等非软件开发工作流的 LangGraph 节点。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anaagent.workflow.nodes import (
    _append_agent_output,
    _collect_artifacts,
    _extract_json_object,
    _get_state_value,
    _record_usage_from_llm,
    call_llm,
    execute_tool_calls,
    parse_tool_calls,
)
from anaagent.workflow.state import AgentOutput, AgentRole, WorkflowStage, WorkflowState

# 工具协议：与工程团队共用同一套运行时，但角色上你不是开发者——工具只用来「把文稿保存到磁盘」
CONTENT_TOOL_JSON_SPEC = """
你必须只输出一个 JSON 对象（不要使用 markdown 代码围栏），格式如下：
{
  "summary": "本轮一句话说明（面向编辑，不要写成技术方案摘要）",
  "actions": [
    {"tool":"write_file","args":{"path":"相对路径","content":"完整文件内容","mode":"overwrite"}},
    {"tool":"read_file","args":{"path":"相对路径"}}
  ],
  "notes": "可选"
}
可用工具：read_file、write_file(mode=overwrite|append)、run_shell（须符合白名单）、git_status。
path 均为相对工作区根目录。必须用 write_file 把文稿写入磁盘；不要用 JSON 外的长篇闲聊代替落盘。
【关键】write_file 的 args.content 只能是「文稿正文全文」（读者打开文件就能读的那一类），禁止把 content 填成编程教程、自动化方案或脚本清单。
"""

_NON_DEV_ARTICLE_PERSONA = """
【角色边界（必须遵守）】
你是「文章撰写」团队的编辑与作者，不是软件开发团队，也不是自动化工程师。
- 禁止撰写：技术选型、实施方案、MVP、接口设计、脚本教程、测试验收、工程排期类体裁。
- 用户若提到「工作目录 / Markdown 文件」，仅表示交付格式；你要写的是他要读的短文/文章正文，不是「如何用 Python 保存文件」的说明。
- 文中如需示例，用普通句子即可；禁止用大段可运行代码（含 ```python 代码块）冒充正文。
"""

_NON_DEV_RESEARCH_PERSONA = """
【角色边界（必须遵守）】
你是「科研辅助」团队的研究助理与写作编辑，不是软件开发团队。
- 禁止把任务写成「需求分析→技术方案→脚本落地→验收」的软件工程文档，除非用户明确要求写代码。
- 交付物应是综述、科普、研究笔记、结构化观点陈述类 Markdown；不要写成运维脚本手册或自动化报告。
"""

# 文章/创意类：避免模型把「保存为 md」理解成「写 Python 教程」
_ARTICLE_BODY_RULES = """
【正文成品要求（必须遵守）】
- 用 write_file 写入的正文必须是文学/说明类可读文本（故事、短文、杂文、解说稿等）。
- 禁止以编程教程、自动化报告、工程步骤、终端命令说明为主；禁止用脚本实现说明代替「用户要的百字短文」本身。
- 若用户要求约 100 字、固定主题，正文字数与主题必须直接满足；禁止用「扩展建议」「后续优化」等技术文档章节凑篇幅。
"""

# 科研类：同样禁止把「落盘 md」答成写脚本教程
_RESEARCH_BODY_RULES = """
【报告成品要求（必须遵守）】
- write_file 写入的应是面向读者的研究/科普/综述正文。
- 禁止以大段编程教程、可运行脚本、或「如何生成 md」的流程说明代替科研内容。
- 禁止写成软件项目的需求规格书口吻，除非用户明确在做软件课题。
"""


def _record(state: WorkflowState, agent: str, role: AgentRole, stage: str, i: int, o: int, ms: int) -> None:
    _record_usage_from_llm(state, agent, i, o, ms, stage)


def _content_tool_round(
    state: WorkflowState,
    *,
    agent_name: str,
    role: AgentRole,
    usage_stage: str,
    graph_stage: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8192,
) -> tuple[dict[str, Any], AgentOutput, str, int, list[str]]:
    """与 dev_node 相同：LLM 产出 JSON → parse_tool_calls → execute_tool_calls。"""
    workspace_dir = str(Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve())
    content, input_tokens, output_tokens, duration = call_llm(user_prompt, system_prompt, max_tokens=max_tokens)
    _record_usage_from_llm(state, agent_name, input_tokens, output_tokens, duration, usage_stage)
    parsed = _extract_json_object(content)
    parsed_calls, action_errors = parse_tool_calls(parsed.get("actions", []))
    actions = [{"tool": c.tool.value, "args": c.args} for c in parsed_calls]
    tool_results = execute_tool_calls(workspace_dir=workspace_dir, calls=actions)

    ws = Path(workspace_dir).resolve()
    write_paths: list[str] = []
    for r in tool_results:
        if r.get("tool") != "write_file" or not r.get("success"):
            continue
        ap = (r.get("metadata") or {}).get("path", "")
        if not ap:
            continue
        try:
            write_paths.append(str(Path(ap).resolve().relative_to(ws)))
        except ValueError:
            write_paths.append(Path(ap).name)

    successful_writes = sum(1 for r in tool_results if r.get("tool") == "write_file" and r.get("success"))
    artifacts = _collect_artifacts(_get_state_value(state, "artifacts", []), tool_results)

    summary = parsed.get("summary", "") if isinstance(parsed, dict) else ""
    notes = parsed.get("notes", "") if isinstance(parsed, dict) else ""
    results_preview = "\n".join(
        f"- {r.get('tool')}: {'OK' if r.get('success') else 'FAIL'}" for r in tool_results
    )
    action_error_text = "\n".join(f"- {err}" for err in action_errors) if action_errors else "(none)"
    summary_text = (
        f"## Summary\n{summary or '(none)'}\n\n"
        f"## Tool Results\n{results_preview or '(no actions)'}\n\n"
        f"## Validation\n{action_error_text}\n\n"
        f"## Notes\n{notes or '(none)'}"
    )

    output = AgentOutput(
        agent_name=agent_name,
        role=role,
        content=summary_text,
        success=True,
        tokens_used=input_tokens + output_tokens,
        duration_ms=duration,
    )

    existing_calls = _get_state_value(state, "tool_calls", [])
    call_records = existing_calls + [{"stage": graph_stage, **action} for action in actions]
    existing_results = _get_state_value(state, "command_results", [])
    command_results = existing_results + [{**r, "stage": graph_stage} for r in tool_results]
    if action_errors:
        command_results.append(
            {
                "stage": graph_stage,
                "tool": "validation",
                "success": False,
                "error": "; ".join(action_errors),
            }
        )

    updates: dict[str, Any] = {
        "tool_calls": call_records,
        "command_results": command_results,
        "artifacts": artifacts,
    }
    return updates, output, summary_text, successful_writes, write_paths


def article_outline_node(state: WorkflowState) -> dict:
    system = f"""你是资深内容策划编辑。请根据用户主题输出：
1) 目标读者与文体
2) 三级大纲（含每节要点）
3) 关键事实/素材占位（若缺信息请列出需要用户补充的问题）

使用清晰的 Markdown，不要臆造具体数据。
大纲只服务于后续写作，不要写编程实现、自动化方案、文件保存步骤或脚本教程。
{_NON_DEV_ARTICLE_PERSONA}
{_ARTICLE_BODY_RULES}"""
    user_request = _get_state_value(state, "user_request", "")
    task_description = _get_state_value(state, "task_description", "")
    prompt = f"写作主题与要求：\n{user_request}\n\n补充说明：\n{task_description or '无'}\n"
    try:
        content, it, ot, dur = call_llm(prompt, system, max_tokens=4096)
        _record(state, "outline", AgentRole.PM, "article_outline", it, ot, dur)
        out = AgentOutput(
            agent_name="outline",
            role=AgentRole.PM,
            content=content,
            success=True,
            tokens_used=it + ot,
            duration_ms=dur,
        )
        return {
            "pm_output": content,
            "content_outline": content,
            "current_stage": WorkflowStage.PLAN.value,
            "outputs": _append_agent_output(state, out),
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="outline",
            role=AgentRole.PM,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"大纲阶段失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def article_write_node(state: WorkflowState) -> dict:
    """撰写：工具落盘草稿（角色为作者，非开发者）。"""
    system = f"""你是专业作者 Agent（文章撰写团队）。根据大纲，必须用 write_file 在工作区写入完整草稿（建议 draft.md）。
- 分段清晰，有小标题；语言自然
- 如大纲有「待补充」，用中立表述或标注假设
{_NON_DEV_ARTICLE_PERSONA}
{_ARTICLE_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file；actions <= 14；禁止只输出 JSON 而不执行 write_file。
草稿文件的 content 必须是正文 prose，禁止写成技术实施报告。"""
    outline = _get_state_value(state, "content_outline", "") or _get_state_value(state, "pm_output", "")
    user_request = _get_state_value(state, "user_request", "")
    prompt = (
        f"工作区根目录即当前任务目录。\n"
        f"用户主题与要求：\n{user_request}\n\n大纲：\n{outline}\n\n"
        f"请 write_file 写入草稿（建议 draft.md）。若用户要求短文/固定字数，草稿正文必须直接满足。\n"
        f"禁止写「如何用程序保存 Markdown」类内容；只写用户要的文稿。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="writer",
            role=AgentRole.DEVELOPER,
            usage_stage="article_write",
            graph_stage="article_write",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "撰写阶段未执行成功的 write_file，无法在工作区生成草稿文件",
                "outputs": merged,
                **updates,
            }
        draft_rel = rels[-1] if rels else "draft.md"
        return {
            **updates,
            "dev_output": summary_text,
            "content_draft": f"(草稿已写入 {draft_rel})",
            "article_draft_relpath": draft_rel,
            "current_stage": WorkflowStage.DEVELOP.value,
            "outputs": merged,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="writer",
            role=AgentRole.DEVELOPER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"撰写阶段失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def article_polish_node(state: WorkflowState) -> dict:
    """润色：read_file 草稿 + write_file 终稿。"""
    draft_rel = _get_state_value(state, "article_draft_relpath", "draft.md")
    user_request = _get_state_value(state, "user_request", "")
    system = f"""你是资深编辑 Agent（文章撰写团队）。必须先 read_file 读取草稿，再 write_file 写入润色终稿（建议 output/article.md 或 article_final.md）。
- 修正语病与节奏，统一术语；文末附「修订摘要」小节（3-6 条）
- 若草稿是编程/自动化说明而非用户要的短文或文章，按用户原始需求重写为可读正文后再 write_file
{_NON_DEV_ARTICLE_PERSONA}
{_ARTICLE_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file；终稿 content 必须是文稿，不是技术文档。"""
    prompt = (
        f"用户原始需求：\n{user_request}\n\n"
        f"草稿相对路径（请 read_file）：{draft_rel}\n"
        f"请 read_file 后 write_file 输出完整终稿。禁止输出软件开发类自动化方案；只交付润色后的正文。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="editor",
            role=AgentRole.REVIEWER,
            usage_stage="article_polish",
            graph_stage="article_polish",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged_outputs = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "润色阶段未执行成功的 write_file，无法在工作区生成终稿",
                "outputs": merged_outputs,
                **updates,
            }
        final_rel = rels[-1] if rels else "article_final.md"
        workspace_dir = Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve()
        body = ""
        try:
            body = (workspace_dir / final_rel).read_text(encoding="utf-8")
        except Exception:
            body = summary_text
        total_tokens = sum(o.get("tokens_used", 0) for o in merged_outputs)
        total_out = _compose_article_final(state, body, total_tokens)
        persist_note = f"\n\n成品文件（相对工作区）：{final_rel}\n"
        return {
            **updates,
            "review_output": summary_text,
            "final_result": total_out + persist_note,
            "current_stage": WorkflowStage.DONE.value,
            "success": True,
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "outputs": merged_outputs,
            "article_final_relpath": final_rel,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="editor",
            role=AgentRole.REVIEWER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"润色阶段失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def article_direct_write_node(state: WorkflowState) -> dict:
    """单步：write_file 直接落盘成文（作者角色）。"""
    system = f"""你是专业作者 Agent（文章撰写团队）。根据用户主题直接成文，且必须用 write_file 写入工作区（如 article.md）。
- 自拟小标题，分段合理；信息不足处标注「待补充」
{_NON_DEV_ARTICLE_PERSONA}
{_ARTICLE_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file；write_file.content 只能是用户要的文稿正文。"""
    user_request = _get_state_value(state, "user_request", "")
    task_description = _get_state_value(state, "task_description", "")
    prompt = (
        f"主题与要求：\n{user_request}\n\n补充说明：\n{task_description or '无'}\n\n"
        f"请 write_file 写入完整正文。若要求百字短文，正文约百字即可。\n"
        f"禁止撰写脚本教程、自动化实施方案或「如何用 Python 写文件」类文字。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="direct_writer",
            role=AgentRole.DEVELOPER,
            usage_stage="article_direct",
            graph_stage="article_direct",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "直接撰写未执行成功的 write_file",
                "outputs": merged,
                **updates,
            }
        final_rel = rels[-1] if rels else "article.md"
        workspace_dir = Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve()
        body = ""
        try:
            body = (workspace_dir / final_rel).read_text(encoding="utf-8")
        except Exception:
            body = summary_text
        total_tokens = sum(o.get("tokens_used", 0) for o in merged)
        final_body = f"""# 直接撰写结果

## 主题
{user_request}

---

{body}

---

## Token 消耗
约 {total_tokens} tokens

## 成品文件（相对工作区）
{final_rel}
"""
        return {
            **updates,
            "dev_output": summary_text,
            "content_draft": f"(已写入 {final_rel})",
            "final_result": final_body,
            "current_stage": WorkflowStage.DONE.value,
            "success": True,
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "outputs": merged,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="direct_writer",
            role=AgentRole.DEVELOPER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"直接撰写失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def research_requirements_report_node(state: WorkflowState) -> dict:
    """单步：科研选题需求分析 → write_file 落盘（研究口径，非软件需求规格）。"""
    system = f"""你是科研选题与需求分析顾问（科研辅助团队）。必须将「课题/研究需求分析报告」用 write_file 写入工作区（建议 requirements_report.md），结构包含：
1) 背景与目标 2) 范围界定 3) 关键问题与优先级 4) 约束与假设 5) 信息缺口 6) 建议下一步（检索/实验等）
语气客观；勿编造文献。禁止写成软件项目的 SRS/接口规格；不得只输出对话而不 write_file。
{_NON_DEV_RESEARCH_PERSONA}
{_RESEARCH_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file。"""
    user_request = _get_state_value(state, "user_request", "")
    task_description = _get_state_value(state, "task_description", "")
    workspace = _get_state_value(state, "workspace_dir", "")
    extra = ""
    if workspace:
        p = Path(workspace)
        readme = p / "README.md"
        if readme.exists():
            try:
                extra = f"\n\n本地 README 摘录（前 2000 字）：\n{readme.read_text(encoding='utf-8')[:2000]}"
            except Exception:
                pass
    prompt = (
        f"需求/课题描述：\n{user_request}\n\n补充背景：\n{task_description or '无'}{extra}\n\n"
        f"请 write_file 写入完整报告（科研选题口径）。禁止写成软件开发需求规格或自动化方案。\n"
        f"若用户只要一篇约百字短文，报告中正文部分应直接满足该体裁。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="requirements_analyst",
            role=AgentRole.PM,
            usage_stage="research_requirements",
            graph_stage="research_requirements",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "需求分析未执行成功的 write_file",
                "outputs": merged,
                **updates,
            }
        final_rel = rels[-1] if rels else "requirements_report.md"
        workspace_dir = Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve()
        content = ""
        try:
            content = (workspace_dir / final_rel).read_text(encoding="utf-8")
        except Exception:
            content = summary_text
        tokens = sum(o.get("tokens_used", 0) for o in merged)
        final_body = f"""# 需求分析报告

{user_request}

---

{content}

---

## Token 消耗
约 {tokens} tokens

## 成品文件（相对工作区）
{final_rel}
"""
        return {
            **updates,
            "pm_output": summary_text,
            "final_result": final_body,
            "current_stage": WorkflowStage.DONE.value,
            "success": True,
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "outputs": merged,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="requirements_analyst",
            role=AgentRole.PM,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"需求分析失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def _compose_article_final(state: WorkflowState, polished: str, total_tokens: int) -> str:
    req = _get_state_value(state, "user_request", "")
    return f"""# 文章撰写结果

## 主题
{req}

---

{polished}

---

## Token 消耗
约 {total_tokens} tokens
"""


def research_plan_node(state: WorkflowState) -> dict:
    system = f"""你是科研助理（科研辅助团队）。请针对用户问题产出研究计划，不要写成软件开发项目计划：
1) 问题拆解与假设
2) 建议检索关键词与信息源类型（文献/数据/政策等）
3) 预期产出结构（科普/综述章节）
4) 风险与局限（简明）

使用 Markdown。勿编造具体文献条目；禁止出现「技术选型」「接口」「迭代」「MVP」等软件工程用语，除非用户课题本就是软件开发。
{_NON_DEV_RESEARCH_PERSONA}
{_RESEARCH_BODY_RULES}"""
    user_request = _get_state_value(state, "user_request", "")
    task_description = _get_state_value(state, "task_description", "")
    prompt = f"研究问题：\n{user_request}\n\n背景：\n{task_description or '无'}\n"
    try:
        content, it, ot, dur = call_llm(prompt, system, max_tokens=4096)
        _record(state, "research_pm", AgentRole.PM, "research_plan", it, ot, dur)
        out = AgentOutput(
            agent_name="research_plan",
            role=AgentRole.PM,
            content=content,
            success=True,
            tokens_used=it + ot,
            duration_ms=dur,
        )
        return {
            "pm_output": content,
            "research_plan": content,
            "current_stage": WorkflowStage.PLAN.value,
            "outputs": _append_agent_output(state, out),
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="research_plan",
            role=AgentRole.PM,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"研究规划失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def research_synthesize_node(state: WorkflowState) -> dict:
    """综合：write_file 写入 synthesis.md（供报告阶段 read_file）。"""
    system = f"""你是科研助理 Agent（科研辅助团队）。基于研究计划产出「证据卡片」式综合，必须用 write_file 写入 synthesis.md：
- 分主题小节：结论倾向 + 理由 + 不确定性；区分共识/争议/待验证
- 使用 Markdown，避免虚构引用；禁止写成脚本开发说明或自动化流水线文档
{_NON_DEV_RESEARCH_PERSONA}
{_RESEARCH_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file；文件内容为科研综合正文。"""
    plan = _get_state_value(state, "research_plan", "") or _get_state_value(state, "pm_output", "")
    user_request = _get_state_value(state, "user_request", "")
    workspace = _get_state_value(state, "workspace_dir", "")
    extra = ""
    if workspace:
        p = Path(workspace)
        readme = p / "README.md"
        if readme.exists():
            try:
                extra = f"\n\n本地 README 摘录（前 2000 字）：\n{readme.read_text(encoding='utf-8')[:2000]}"
            except Exception:
                pass
    prompt = (
        f"原始问题：{user_request}\n\n研究计划：\n{plan}{extra}\n\n"
        f"请 write_file 写入完整综合稿（建议 synthesis.md）。若用户只要短文，综合稿主体可直接写一篇短文并标明字数。\n"
        f"禁止用 Python 脚本、自动化教程冒充科研综合。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="research_synthesize",
            role=AgentRole.DEVELOPER,
            usage_stage="research_synthesize",
            graph_stage="research_synthesize",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "综合阶段未执行成功的 write_file",
                "outputs": merged,
                **updates,
            }
        syn_rel = rels[-1] if rels else "synthesis.md"
        workspace_dir = Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve()
        syn_text = ""
        try:
            syn_text = (workspace_dir / syn_rel).read_text(encoding="utf-8")
        except Exception:
            syn_text = ""
        return {
            **updates,
            "dev_output": summary_text,
            "research_synthesis": syn_text,
            "research_synthesis_relpath": syn_rel,
            "current_stage": WorkflowStage.DEVELOP.value,
            "outputs": merged,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="research_synthesize",
            role=AgentRole.DEVELOPER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"综合阶段失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }


def research_report_node(state: WorkflowState) -> dict:
    """终稿：read_file 综合稿 + write_file report.md。"""
    syn_rel = _get_state_value(state, "research_synthesis_relpath", "synthesis.md")
    plan = _get_state_value(state, "research_plan", "")
    user_request = _get_state_value(state, "user_request", "")
    synthesis_excerpt = (_get_state_value(state, "research_synthesis", "") or "")[:12000]
    system = f"""你是科研写作编辑 Agent（科研辅助团队）。必须先 read_file 读取综合稿，再 write_file 写入最终稿（建议 report.md）。
报告面向读者：摘要、方法与范围、主要观点、局限性、后续可做检索；语气客观科普/综述向。
禁止写成软件上线报告、自动化运维文档或脚本手册；若综合稿含无关编程教程，成稿中剔除。
{_NON_DEV_RESEARCH_PERSONA}
{_RESEARCH_BODY_RULES}
{CONTENT_TOOL_JSON_SPEC}
硬性约束：至少 1 次成功的 write_file；report.md 正文须是可读的科研/科普文稿。"""
    prompt = (
        f"用户问题：\n{user_request}\n\n"
        f"研究计划（摘要）：\n{plan[:4000]}\n\n"
        f"综合稿相对路径（请 read_file）：{syn_rel}\n\n"
        f"若 read 失败可参考以下摘录：\n{synthesis_excerpt}\n\n"
        f"请 read_file 后 write_file 输出完整 report.md。"
        f"若用户仅要一篇约百字短文，report.md 主体可直接为该短文（勿附脚本教程）。"
    )
    try:
        updates, out, summary_text, write_ok, rels = _content_tool_round(
            state,
            agent_name="research_report",
            role=AgentRole.REVIEWER,
            usage_stage="research_report",
            graph_stage="research_report",
            system_prompt=system,
            user_prompt=prompt,
        )
        merged_outputs = _append_agent_output(state, out)
        if write_ok < 1:
            return {
                "current_stage": WorkflowStage.FAILED.value,
                "success": False,
                "error_message": "报告阶段未执行成功的 write_file",
                "outputs": merged_outputs,
                **updates,
            }
        final_rel = rels[-1] if rels else "report.md"
        workspace_dir = Path(_get_state_value(state, "workspace_dir", str(Path.cwd()))).expanduser().resolve()
        content = ""
        try:
            content = (workspace_dir / final_rel).read_text(encoding="utf-8")
        except Exception:
            content = summary_text
        tokens = sum(o.get("tokens_used", 0) for o in merged_outputs)
        total = f"""# 科研辅助报告

{user_request}

---

{content}

---

## Token 消耗
约 {tokens} tokens

## 成品文件（相对工作区）
{final_rel}
"""
        return {
            **updates,
            "review_output": summary_text,
            "final_result": total,
            "current_stage": WorkflowStage.DONE.value,
            "success": True,
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "outputs": merged_outputs,
        }
    except Exception as exc:
        out = AgentOutput(
            agent_name="research_report",
            role=AgentRole.REVIEWER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"报告阶段失败: {exc}",
            "outputs": _append_agent_output(state, out),
        }

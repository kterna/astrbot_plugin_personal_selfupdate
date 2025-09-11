from typing import Any, Iterable, Optional


def _format_begin_dialogs(begin_dialogs: Optional[Iterable[str]]) -> str:
    if not begin_dialogs:
        return "无"
    try:
        return "\n".join([f"  - {d}" for d in begin_dialogs])
    except Exception:
        return "无"


def _format_tools(tools: Any) -> str:
    # None -> 默认全部; [] -> 无; list/tuple -> join
    if tools is None:
        return "默认全部"
    if isinstance(tools, (list, tuple)):
        if len(tools) == 0:
            return "无"
        try:
            return ", ".join(tools)
        except Exception:
            return str(tools)
    return str(tools)


def build_persona_detail_text(persona_id: str, persona: Any) -> str:
    """构建单个人格的详细信息文本。"""
    response_text = f"以下是人格 '{persona_id}' 的详细信息：\n"
    system_prompt = getattr(persona, "system_prompt", "")
    response_text += f"- 系统提示 (System Prompt):\n---\n{system_prompt}\n---\n"

    begin_dialogs = getattr(persona, "begin_dialogs", None)
    dialogs = _format_begin_dialogs(begin_dialogs)
    response_text += f"- 开场白 (Begin Dialogs):\n{dialogs}\n"

    tools = getattr(persona, "tools", None)
    tools_text = _format_tools(tools)
    response_text += f"- 工具 (Tools): {tools_text}"

    return response_text


def build_persona_list_text(personas: Iterable[Any]) -> str:
    """构建人格列表的展示文本。"""
    response_text = "📖 数据库中的人格列表：\n"
    for i, p in enumerate(personas):
        response_text += f"---------- {i + 1} ----------\n"
        response_text += f"👤 人格ID: {getattr(p, 'persona_id', '')}\n"
        response_text += f"📝 系统提示: {getattr(p, 'system_prompt', '')}\n"

        begin_dialogs_text = _format_begin_dialogs(getattr(p, "begin_dialogs", None))
        response_text += f"💬 开场白: {begin_dialogs_text}\n"

        tools_text = _format_tools(getattr(p, "tools", None))
        response_text += f"🛠️ 工具: {tools_text}\n"

    response_text += "\n"
    return response_text


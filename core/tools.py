from typing import Optional
from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
import json

# Forward declaration for type hinting
if False:
    from ..main import Main

class GetPersonaDetailTool(FunctionTool):
    def __init__(self, main_plugin: "Main", event: "AstrMessageEvent"):
        self.main_plugin = main_plugin
        self.event = event
        
        super().__init__(
            name="get_persona_detail",
            description="获取指定ID的人格的详细信息。",
            parameters={
                "type": "object",
                "properties": {
                    "persona_id": {
                        "type": "string",
                        "description": "要查询的人格的ID。"
                    }
                },
                "required": ["persona_id"]
            },
            handler=self._run_handler,
            handler_module_path=__name__
        )
    
    async def _run_handler(self, **kwargs):
        persona_id = kwargs.get('persona_id')
        logger.info(f"[Tool] GetPersonaDetailTool: 查询人格 '{persona_id}' 的详细信息")
        try:
            persona = await self.main_plugin.context.persona_manager.get_persona(persona_id)
            logger.info(f"[Tool] GetPersonaDetailTool: 成功获取人格 '{persona_id}' 信息")
            result = {
                "persona_id": persona_id,
                "system_prompt": getattr(persona, "system_prompt", ""),
                "begin_dialogs": getattr(persona, "begin_dialogs", []),
                "tools": getattr(persona, "tools", None)
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Tool] GetPersonaDetailTool: 获取人格 '{persona_id}' 失败: {e}")
            return f"错误：{e}"

class UpdatePersonaDetailsTool(FunctionTool):
    def __init__(self, main_plugin: "Main", event: "AstrMessageEvent"):
        self.main_plugin = main_plugin
        self.event = event
        
        super().__init__(
            name="update_persona_details",
            description="更新指定ID的人格信息。只有提供的参数才会被更新。",
            parameters={
                "type": "object",
                "properties": {
                    "persona_id": {
                        "type": "string",
                        "description": "要更新的人格的ID。"
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "新的系统提示。"
                    },
                    "begin_dialogs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "新的开场白列表。"
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "新的工具列表。None表示默认全部，空列表表示无。"
                    }
                },
                "required": ["persona_id"]
            },
            handler=self._run_handler,
            handler_module_path=__name__
        )
    
    async def _run_handler(self, **kwargs):
        persona_id = kwargs.get('persona_id')
        system_prompt = kwargs.get('system_prompt')
        begin_dialogs = kwargs.get('begin_dialogs')
        tools = kwargs.get('tools')
        
        logger.info(f"[Tool] UpdatePersonaDetailsTool: 更新人格 '{persona_id}' - system_prompt: {bool(system_prompt)}, begin_dialogs: {bool(begin_dialogs)}, tools: {bool(tools)}")
        
        success, message = await self.main_plugin._update_persona(
            persona_id=persona_id,
            system_prompt=system_prompt,
            begin_dialogs=begin_dialogs,
            tools=tools,
        )
        
        if success:
            logger.info(f"[Tool] UpdatePersonaDetailsTool: 成功更新人格 '{persona_id}'")
            try:
                persona = await self.main_plugin.context.persona_manager.get_persona(persona_id)
                result = {
                    "persona_id": persona_id,
                    "system_prompt": getattr(persona, "system_prompt", ""),
                    "begin_dialogs": getattr(persona, "begin_dialogs", []),
                    "tools": getattr(persona, "tools", None)
                }
                logger.info(f"[Tool] UpdatePersonaDetailsTool: 返回更新后的人格信息")
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[Tool] UpdatePersonaDetailsTool: 获取更新后信息失败: {e}")
                return f"更新成功但获取更新后信息失败：{e}"
        else:
            logger.error(f"[Tool] UpdatePersonaDetailsTool: 更新人格 '{persona_id}' 失败: {message}")
            return message

from astrbot.api.star import Star, Context, register
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from typing import Optional
from astrbot.api.provider import LLMResponse
from astrbot.api import AstrBotConfig, logger, ToolSet
from .core.tools import GetPersonaDetailTool, UpdatePersonaDetailsTool
from .core.textbuild import (
    build_persona_detail_text,
    build_persona_list_text,
)

@register(
    "personal_selfupdate",
    "kterna",
    "通过与LLM对话来更新人格",
    "0.1.0",
    "https://github.com/kterna/astrbot_plugin_personal_selfupdate"
)
class Main(Star):
    def __init__(self, context: Context) -> None:
        """
        插件初始化
        """
        super().__init__(context)
        self.config = self.context.get_config()

    async def _get_persona_detail(self, event: AstrMessageEvent, persona_id: str) -> MessageEventResult:
        """
        获取指定ID的人格的详细信息。

        :param persona_id: 要查询的人格的ID。
        """
        try:
            persona = await self.context.persona_manager.get_persona(persona_id)
            return event.plain_result(build_persona_detail_text(persona_id, persona))
        except ValueError as e:
            return event.plain_result(f"错误：{e}")
        except Exception as e:
            return event.plain_result(f"查询人格详情时出错: {e}")

    @filter.command("人格详情", "persona detail")
    async def persona_detail(self, event: AstrMessageEvent):
        """
        获取指定ID的人格的详细信息。
        用法: /人格详情 [人格ID]
        """
        args = event.message_str.split()
        if len(args) < 2:
            yield event.plain_result("参数不足，请提供人格ID。用法: /人格详情 [人格ID]")
            return

        persona_id = args[1]
        result = await self._get_persona_detail(event, persona_id)
        yield result

    @filter.command("人格列表", "persona list")
    async def persona_list(self, event: AstrMessageEvent):
        """
        查看数据库中所有的人格数据
        """
        try:
            # 1. 从上下文中获取 PersonaManager
            persona_manager = self.context.persona_manager

            # 2. 获取所有人格数据
            # get_all_personas_v3 返回的是配置中的人格，get_all_personas 返回的是数据库中的
            personas = await persona_manager.get_all_personas()
            if not personas:
                yield event.plain_result("数据库中没有任何人格设定")
                return
            response_text = build_persona_list_text(personas)
            yield event.plain_result(response_text)
        except Exception as e:
            yield event.plain_result(f"获取人格列表失败: {e}")

    async def _update_persona(
        self,
        persona_id: str,
        system_prompt: Optional[str] = None,
        begin_dialogs: Optional[list] = None,
        tools: Optional[list] = None,
    ):
        """
        内部方法：根据 persona_id 更新人格数据。
        对于值为 None 的参数，将不会进行修改。

        :param persona_id: 要更新的人格ID
        :param system_prompt: 新的系统提示
        :param begin_dialogs: 新的开场白列表
        :param tools: 新的工具列表
        """
        try:
            persona_manager = self.context.persona_manager
            
            # 构造需要更新的数据
            update_data = {}
            if system_prompt is not None:
                update_data["system_prompt"] = system_prompt
            if begin_dialogs is not None:
                update_data["begin_dialogs"] = begin_dialogs
            if tools is not None:
                update_data["tools"] = tools

            # 如果没有提供任何更新，则直接返回
            if not update_data:
                return True, f"未提供任何需要更新的字段，人格 '{persona_id}' 未作修改。"

            # 调用 PersonaManager 来更新数据，它会处理数据库和缓存
            # update_persona 内部会检查人格是否存在
            await persona_manager.update_persona(persona_id, **update_data)
            
            return True, f"成功更新人格 '{persona_id}'。"
        except Exception as e:
            return False, f"更新人格 '{persona_id}' 失败: {e}"

    @filter.command("人格更新", "persona update")
    async def persona_self_update(self, event: AstrMessageEvent):
        """
        通过独立的Agent流程，让LLM自我更新人格。
        用法: /人格更新 [人格ID] [更新要求]
        例如: /人格更新 伯特 让他说话更专业一些
        """
        args = event.message_str.split(" ")
        if len(args) < 3:
            yield event.plain_result("参数不足，请提供人格ID和更新要求。")
            return

        persona_id = args[1]
        update_requirement = " ".join(args[2:])
        logger.info(f"收到人格更新命令. ID: '{persona_id}', 要求: '{update_requirement}'")

        # 1. 定义在此次会话中生效的工具
        tool_set = ToolSet([
            GetPersonaDetailTool(main_plugin=self, event=event),
            UpdatePersonaDetailsTool(main_plugin=self, event=event),
        ])
        
        logger.info(f"创建 ToolSet，包含工具: {tool_set.names()}")
        logger.info(f"ToolSet 长度: {len(tool_set)}")
        for tool in tool_set:
            logger.info(f"工具详情: {tool.name} - {tool.description} - Handler: {tool.handler is not None}")

        # 2. 获取 Provider
        provider_config = self.config.get("provider")
        model_name = self.config.get("model")
        
        # 处理配置值可能是列表的情况
        if isinstance(provider_config, list):
            provider_config = provider_config[0] if provider_config else None
        if isinstance(model_name, list):
            model_name = model_name[0] if model_name else None
            
        # 从 provider 配置中提取 ID
        provider_id = None
        if provider_config:
            if isinstance(provider_config, dict):
                provider_id = provider_config.get("id")
            elif isinstance(provider_config, str) and provider_config != "":
                provider_id = provider_config
        
        # 确保 model_name 为字符串或None
        model_name = str(model_name) if model_name and model_name != "" else None
        
        logger.info(f"插件配置 - Provider ID: '{provider_id or '默认'}' Model: '{model_name or '默认'}'")

        try:
            if provider_id:
                provider = self.context.get_provider_by_id(provider_id=provider_id)
            else:
                provider = self.context.get_using_provider(umo=event.unified_msg_origin)
            if not provider:
                raise ValueError("无法获取有效的服务提供商。")
        except Exception as e:
            logger.error(f"获取服务提供商失败: {e}", exc_info=True)
            yield event.plain_result(f"获取服务提供商失败: {e}")
            return

        # 3. 构建 System Prompt，让 LLM 自行决定如何使用工具
        system_prompt = f"""你是人格配置专家，负责根据用户要求更新 AI 人格设定。

可用工具：
- get_persona_detail(persona_id): 获取人格当前设定
- update_persona_details(persona_id, system_prompt?, begin_dialogs?, tools?): 更新人格设定

任务：更新人格 '{persona_id}'，要求：{update_requirement}

步骤：1. 先获取当前设定 2. 根据要求修改 3. 应用更新 4. 简洁总结修改内容"""
        user_prompt = "开始执行。"
        
        logger.info("开始调用 LLM Agent 进行人格更新")
        yield event.plain_result("🔄 分析中...")

        try:
            logger.info("调用 LLM Agent，让其自主使用工具...")
            logger.info(f"传递给 provider.text_chat 的工具类型: {type(tool_set)}")
            logger.info(f"工具 openai_schema: {tool_set.openai_schema()}")
            
            # 单次调用，框架会自动处理工具调用循环
            response: LLMResponse = await provider.text_chat(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model_name or None,
                func_tool=tool_set,
                session_id=None,  # 不使用会话
                contexts=[],      # 不使用上下文
                image_urls=[]     # 不使用图片
            )

            logger.info(f"LLM 响应对象: {response}")
            logger.info(f"LLM 响应角色: {getattr(response, 'role', 'None')}")
            logger.info(f"LLM 响应内容长度: {len(getattr(response, 'completion_text', ''))}")
            logger.info(f"LLM 是否有工具调用: {hasattr(response, 'tool_calls')}")
            if hasattr(response, 'tool_calls'):
                logger.info(f"工具调用内容: {getattr(response, 'tool_calls', 'None')}")

            final_text = response.completion_text if response else "响应为空"
            logger.info(f"LLM Agent 执行完成，总结: {final_text[:100]}...")
            
            # 精简返回文本
            if "总结" in final_text:
                summary_start = final_text.find("总结")
                if summary_start != -1:
                    final_text = final_text[summary_start:]
            
            yield event.plain_result(f"✅ 更新完成\n{final_text}")

        except Exception as e:
            logger.error(f"执行人格更新 Agent 流程时出错: {e}", exc_info=True)
            yield event.plain_result(f"❌ 更新失败: {e}")

from astrbot.api.star import Star, Context, register
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.provider import LLMResponse
from astrbot.api import AstrBotConfig, logger, ToolSet

from .core.tools import GetPersonaDetailTool, UpdatePersonaDetailsTool

import json

@register(
    "personal_selfupdate",
    "kterna",
    "通过与LLM对话来更新人格",
    "0.1.0",
    "https://github.com/kterna/astrbot_plugin_personal_selfupdate"
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        """
        插件初始化
        """
        super().__init__(context)
        self.config = config

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("人格更新", "persona update")
    async def persona_self_update(self, event: AstrMessageEvent):
        """
        通过独立的Agent流程，让LLM自我更新人格。
        用法: /人格更新 [人格ID] [更新要求]
        例如: /人格更新 伯特 让他说话更专业一些
        """
        raw_message = event.message_str.strip()
        parts = raw_message.split(None, 2) if raw_message else []

        if len(parts) < 3:
            yield event.plain_result("参数不足，请提供人格ID和更新要求。")
            return

        _, persona_id, update_requirement = parts
        persona_id = persona_id.strip()
        update_requirement = update_requirement.strip()

        if not persona_id:
            yield event.plain_result("人格ID 不能为空，请重新输入。")
            return

        if not update_requirement:
            yield event.plain_result("更新要求不能为空，请提供具体说明。")
            return
        logger.info(f"收到人格更新命令. ID: '{persona_id}', 要求: '{update_requirement}'")

        # 1. 定义在此次会话中生效的工具
        tool_set = ToolSet([
            GetPersonaDetailTool(main_plugin=self, event=event),
            UpdatePersonaDetailsTool(main_plugin=self, event=event),
        ])

        # 2. 获取 Provider
        provider_id = str(self.config.get("provider", "") or "").strip()
        model_name = self.config.get("model", "")

        # 处理 model 配置
        model_name = str(model_name) if model_name and model_name != "" else None

        try:
            provider_instance = None

            if provider_id:
                # 如果指定了 provider ID，尝试获取该 provider
                provider_instance = self.context.get_provider_by_id(provider_id=provider_id)
                if not provider_instance:
                    logger.warning(f"指定的 Provider '{provider_id}' 不存在或未启用，使用默认 provider")
                    provider_instance = self.context.get_using_provider(umo=event.unified_msg_origin)
            else:
                # 没有指定，使用默认
                provider_instance = self.context.get_using_provider(umo=event.unified_msg_origin)

            if not provider_instance:
                raise ValueError("无法获取有效的服务提供商。请检查是否有启用的 Provider。")

        except Exception as e:
            logger.error(f"获取服务提供商失败: {e}", exc_info=True)
            yield event.plain_result(f"获取服务提供商失败: {e}")
            return

        provider = provider_instance

        # 3. 构建 System Prompt，让 LLM 自行决定如何使用工具
        system_prompt = f"""你是人格配置专家，负责根据用户要求更新 AI 人格设定。
可用工具：
- get_persona_detail(persona_id): 获取人格当前设定 - 必须先调用
- update_persona_details(persona_id, system_prompt?, begin_dialogs?, tools?): 更新人格设定,begin_dialogs为偶数个字符串，每个字符串代表一个对话，用户和助手轮流对话

任务：更新人格 '{persona_id}'，要求：{update_requirement}

重要：你必须严格按以下步骤执行：
1. 调用 get_persona_detail 获取当前人格信息
2. 根据要求分析需要修改的内容  
3. 调用 update_persona_details 应用修改
4. 简洁总结修改内容

请严格按照上述流程执行。特别注意：
- begin_dialogs 必须包含偶数条对话，且需按照“用户、助手”轮流排列。
- 只有在完成分析并确定改动后，才调用一次 update_persona_details 应用修改。

请立即开始执行，先调用 get_persona_detail 工具。"""
        user_prompt = "开始执行。"
        
        logger.info("开始调用 LLM Agent 进行人格更新")
        yield event.plain_result("🔄 分析中...")

        try:
            logger.info("开始 LLM Agent 工具调用...")
            
            max_iterations = 10
            
            messages = []
            current_prompt = user_prompt

            for _ in range(max_iterations):

                response: LLMResponse = await provider.text_chat(
                    prompt=current_prompt,
                    system_prompt=system_prompt,
                    model=model_name or None,
                    func_tool=tool_set,
                    session_id=None,
                    contexts=messages,
                    image_urls=[]
                )
                
                messages.append({"role": "user", "content": current_prompt})
                
                # 检查是否有工具调用
                if (hasattr(response, 'tools_call_name') and 
                    hasattr(response, 'tools_call_args') and 
                    response.tools_call_name and 
                    response.tools_call_args):
                    
                    # 执行所有工具调用
                    tool_results = []
                    tool_call_ids = getattr(response, 'tools_call_ids', [f"{name}:{i}" for i, name in enumerate(response.tools_call_name)])
                    
                    for tool_name, tool_args, tool_id in zip(
                        response.tools_call_name, 
                        response.tools_call_args,
                        tool_call_ids
                    ):
                        # 获取工具并执行
                        tool = tool_set.get_tool(tool_name)
                        if tool and tool.handler:
                            try:
                                result = await tool.handler(**tool_args)
                                tool_results.append({
                                    "tool_call_id": tool_id,
                                    "role": "tool",
                                    "content": str(result)
                                })
                            except Exception as e:
                                logger.error(f"工具 {tool_name} 执行失败: {e}")
                                tool_results.append({
                                    "tool_call_id": tool_id,
                                    "role": "tool", 
                                    "content": f"工具执行失败: {e}"
                                })
                        else:
                            logger.error(f"未找到工具: {tool_name}")
                            tool_results.append({
                                "tool_call_id": tool_id,
                                "role": "tool",
                                "content": f"未找到工具: {tool_name}"
                            })
                    
                    # 助理回复
                    assistant_content = "调用工具"
                    if response.result_chain and response.result_chain.chain:
                        text = response.result_chain.chain[0].text
                        if text and text.strip():
                            assistant_content = text
                    
                    # 将助理的回复（包含工具调用）添加到历史
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                        "tool_calls": [
                            {
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                                }
                            }
                            for tool_name, tool_args, tool_id in zip(
                                response.tools_call_name,
                                response.tools_call_args, 
                                tool_call_ids
                            )
                        ]
                    })
                    
                    # 添加工具结果
                    messages.extend(tool_results)
                    
                    # 为下一轮准备：prompt 是一个占位符，以避免空消息错误
                    current_prompt = " "
                    
                    continue
                
                else:
                    # 没有工具调用，完成
                    final_text = response.completion_text if hasattr(response, 'completion_text') else ""
                    if response.result_chain and response.result_chain.chain:
                        final_text = response.result_chain.chain[0].text
                    
                    break
            
            else:
                # 达到最大迭代次数
                final_text = "工具调用超过最大次数限制"
                logger.warning("工具调用循环达到最大次数限制")
            
            # 精简返回文本
            if "总结" in final_text:
                summary_start = final_text.find("总结")
                if summary_start != -1:
                    final_text = final_text[summary_start:]
            
            yield event.plain_result(f"✅ 更新完成\n{final_text}")

        except Exception as e:
            logger.error(f"执行人格更新 Agent 流程时出错: {e}", exc_info=True)
            yield event.plain_result(f"❌ 更新失败: {e}")

from typing import Dict
from nonebot import on_command, on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Event, Message, GroupMessageEvent, MessageSegment
from utils.rules import allow_group_rule, group_owner_admin_rule
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.rule import to_me

from plugins.group_msg_collect import MessageRecorderAPI
from plugins.group_msg_collect import on_message_save
from chat.agents import GroupChatAgent
from chat.core.llm import LLMClient
from chat.core.config import Config
from chat.memory import MemoryConfig

# 全局 Agent 缓存：group_id -> GroupChatAgent
group_agents: Dict[str, GroupChatAgent] = {}

def get_group_agent(group_id: str) -> GroupChatAgent:
    """获取或创建群组对应的 Agent"""
    if group_id not in group_agents:
        logger.info(f"Initializing new GroupChatAgent for group {group_id}")
        
        # 1. 初始化 LLM (建议从 NoneBot 配置或环境变量读取)
        # 这里假设 LLMClient 会自动读取环境变量 OPENAI_API_KEY 等
        llm_client = LLMClient()
        
        # 2. 初始化配置
        config = Config()
        memory_config = MemoryConfig() # 默认使用 ./memory_data 目录
        
        # 3. 创建 Agent
        agent = GroupChatAgent(
            name="HiasBot",  # 机器人名字
            llm=llm_client,
            group_id=group_id,
            config=config,
            memory_config=memory_config,
            enable_memory=True
        )
        group_agents[group_id] = agent
        
    return group_agents[group_id]

__plugin_meta__ = PluginMetadata(
    name="群聊机器人",
    description="基于群聊的智能问答机器人",
    usage="在群聊中@机器人进行对话",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

chat_at = on_message(rule=to_me() & allow_group_rule, priority=10, block=False)


@on_message_save
def handle_new_message(message, message_str):
    """
    处理新消息，写入记忆

    :param message: 消息对象
    :param message_str: 消息文本
    """
    try:
        target_group = str(message.get("group_id"))
        user_id = str(message.get("user_id", "unknown"))
        
        agent = get_group_agent(target_group)
        
        # 将群聊消息存入 Working Memory 作为上下文
        # 注意：这里只存不回复
        agent.add_memory(
            content=message_str,
            memory_type="working",
            user_id=user_id,
            metadata={"source": "group_chat_stream"}
        )
    except Exception as e:
        logger.warning(f"Failed to save group message to memory: {e}")

driver = get_driver()

@driver.on_startup
async def startup():
    # 启动初始化 如果需要
    pass

def get_reply_chain(message_id: str) -> list[str]:
    """获取消息回复链的文本内容"""
    # 假设 MessageRecorderAPI 返回的是字符串列表，如果不是需要转换
    reply_chain = MessageRecorderAPI.get_reply_chain(message_id)
    if isinstance(reply_chain, str):
        return [reply_chain]
    return reply_chain or []


@chat_at.handle()
async def handle_chat(bot: Bot, event: GroupMessageEvent):
    try:
        group_id = str(event.group_id)
        user_id = str(event.user_id)
        query = event.get_plaintext().strip()
        
        if not query:
            await chat_at.finish()

        agent = get_group_agent(group_id)
        reply_context = get_reply_chain(str(event.message_id))
        
        # 调用 Agent 进行回复
        # 注意：run 方法内部会自动将 query 和 response 存入 memory
        answer = await agent.run(
            query=query,
            user_id=user_id,
            reply_string=reply_context
        )
        
        reply_msg = MessageSegment.reply(event.message_id) + answer
        await chat_at.finish(reply_msg)
        
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await chat_at.finish(f"抱歉，发生错误了：{str(e)} 😢 请稍后再试或联系管理员。")
    

# 仅允许群聊且为群主/管理员的命令
chat_debug = on_command("chat_debug", rule=group_owner_admin_rule, priority=5, block=True)

@chat_debug.handle()
async def handle_chat_debug(bot: Bot, event: GroupMessageEvent):
    try:
        debug_info = "群聊机器人调试信息：\n"
        current_group_id = str(event.group_id)
        working_memories_stats = group_agents[current_group_id].memory_manager.memory_types['working'].get_stats()
        debug_info += f"工作记忆统计信息：\n{working_memories_stats}\n"
        episodic_memories_stats = group_agents[current_group_id].memory_manager.memory_types['episodic'].get_stats()
        debug_info += f"情景记忆统计信息：\n{episodic_memories_stats}\n"
        unconsolidated_count = group_agents[current_group_id].memory_manager.get_unconsolidated_count()
        debug_info += f"未整理的情景记忆数量：{unconsolidated_count}\n"
        await chat_debug.finish(debug_info)
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"Chat debug error: {e}")
        await chat_debug.finish(f"抱歉，获取调试信息时发生错误：{str(e)} 😢 请稍后再试或联系管理员。")
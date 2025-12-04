from typing import Dict
from nonebot import on_command, on_message, get_driver, logger, require
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
        logger.info(f"正在为群组 {group_id} 初始化新的 GroupChatAgent")
        
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
        logger.warning(f"保存群消息到记忆失败: {e}")

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
        logger.error(f"聊天处理错误: {e}")
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
        logger.error(f"聊天调试错误: {e}")
        await chat_debug.finish(f"抱歉，获取调试信息时发生错误：{str(e)} 😢 请稍后再试或联系管理员。")

# 定时任务：整理记忆
try:
    require("nonebot_plugin_apscheduler")
    from nonebot_plugin_apscheduler import scheduler

    @scheduler.scheduled_job("interval", hours=1, id="chat_memory_consolidation")
    async def run_memory_consolidation():
        logger.info("[Chat] 开始执行定时记忆整理任务...")
        # 遍历所有已加载的群组 Agent
        for group_id, agent in list(group_agents.items()):
            try:
                manager = agent.memory_manager
                # 获取未整理的记忆数量
                count = manager.get_unconsolidated_count()
                
                # 如果未整理数量超过 100，触发整理流程
                if count > 100:
                    logger.info(f"[Chat] 群组 {group_id} 有 {count} 条未整理记忆，触发整理流程。")
                    
                    # 循环整理，直到未整理数量小于 50
                    while count >= 50:
                        # 每次处理 50 条
                        # 注意：consolidate_memories 内部会自动创建 LLMClient 如果未提供
                        await manager.consolidate_memories(limit=50)
                        
                        # 重新获取数量以检查进度
                        new_count = manager.get_unconsolidated_count()
                        logger.debug(f"[Chat] 群组 {group_id} 剩余未整理记忆: {new_count}")
                        
                        # 死循环保护：如果数量没有减少（说明整理可能失败或无有效内容），强制跳出
                        if new_count >= count:
                            logger.warning(f"[Chat] 群组 {group_id} 记忆数量未减少 ({count} -> {new_count})。为防止死循环，中止整理。")
                            break
                        
                        count = new_count
                        
                    logger.info(f"[Chat] 群组 {group_id} 整理完成。最终数量: {count}")
            except Exception as e:
                logger.error(f"[Chat] 群组 {group_id} 记忆整理过程中出错: {e}")

except Exception as e:
    logger.warning(f"加载 apscheduler 失败，定时任务将不会运行: {e}")
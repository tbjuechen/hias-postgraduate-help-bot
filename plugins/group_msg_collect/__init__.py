from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="消息记录器",
    description="记录群聊消息到数据库，提供查询接口",
    usage="自动记录所有群消息，提供查询API",
    supported_adapters={"~onebot.v11"},
)

from .model import MessageRecord
from .query import MessageRecorderAPI

__all__ = ["MessageRecorderAPI", "MessageRecord"]

from nonebot import on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.typing import T_State

from .model import MessageRecord, init_database, engine, SessionLocal, sessionmaker

import asyncio
import json
from typing import List
from datetime import datetime

# 驱动器事件
driver = get_driver()

@driver.on_startup
async def startup():
    """启动时初始化"""
    logger.info("消息记录器已启动")

@driver.on_shutdown
async def shutdown():
    """关闭时清理"""
    logger.info("消息记录器已关闭")

def extract_message_info(event: GroupMessageEvent, bot: Bot) -> dict:
    """提取消息信息"""
    # 获取消息类型
    message_types = []
    for segment in event.message:
        message_types.append(segment.type)
    
    primary_type = "text"
    if "image" in message_types:
        primary_type = "image"
    elif "voice" in message_types:
        primary_type = "voice"
    elif "video" in message_types:
        primary_type = "video"
    elif "file" in message_types:
        primary_type = "file"
    
    # 提取回复信息
    reply_to = None
    if event.reply:
        reply_to = str(event.reply.message_id) if event.reply.message_id else None
    
    # 获取纯文本
    plain_text = event.get_plaintext().strip()
    
    # 修复消息链序列化
    try:
        message_chain_data = []
        for seg in event.message:
            message_chain_data.append({
                "type": seg.type,
                "data": seg.data
            })
        message_chain_json = json.dumps(message_chain_data)
    except Exception as e:
        logger.warning(f"消息链序列化失败: {e}")
        message_chain_json = json.dumps([])
    
    return {
        "message_id": str(event.message_id),
        "bot_id": str(bot.self_id),
        "platform": "onebot-v11",
        "group_id": event.group_id,
        "user_id": event.user_id,
        "user_name": event.sender.nickname or "",
        "user_card": event.sender.card or "",
        "message_type": primary_type,
        "raw_message": str(event.raw_message),
        "plain_text": plain_text,
        "message_chain": message_chain_json,
        "created_at": datetime.fromtimestamp(event.time),
        "reply_to_message_id": reply_to,
    }

async def save_message_to_db(msg_info: dict):
    """直接保存单条消息到数据库"""
    session = SessionLocal()
    try:
        record = MessageRecord(**msg_info)
        session.add(record)
        session.commit()
        logger.debug(f"消息已保存到数据库: {msg_info['message_id']}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"保存消息失败: {e}")
    finally:
        session.close()

# 消息记录器
message_recorder = on_message(priority=1, block=False)

@message_recorder.handle()
async def record_message(bot: Bot, event: GroupMessageEvent, state: T_State):
    """记录群消息"""
    try:
        msg_info = extract_message_info(event, bot)
        await save_message_to_db(msg_info)
            
    except Exception as e:
        logger.error(f"记录消息失败: {e}")

# 记录机器人发言
async def record_bot_message(bot: Bot, group_id: int, message: List, message_id: str = None, reply_to_message_id: str = None):
    """记录机器人发言"""
    try:
        if SessionLocal is None:
            return

        # 构造机器人消息记录
        bot_msg_info = {
            "message_id": message_id or f"bot_{int(datetime.now().timestamp() * 1000)}",
            "bot_id": str(bot.self_id),
            "platform": "onebot-v11",
            "group_id": group_id,
            "user_id": int(bot.self_id),  # 机器人的用户ID
            "user_name": "BOT",
            "user_card": "机器人",
            "message_type": "text",
            "raw_message": str(message),
            "plain_text": gen_message(message),
            "message_chain": json.dumps([seg.__dict__ for seg in message]),
            "created_at": datetime.now(),
            "reply_to_message_id": reply_to_message_id ,
        }
        
        await save_message_to_db(bot_msg_info)
            
    except Exception as e:
        logger.error(f"记录机器人消息失败: {e}")

# Hook 机器人 call_api 方法
original_call_api = None

async def hooked_call_api(self, api: str, **data):
    """Hook call_api 方法"""
    global original_call_api
    
    # 调用原始方法
    result = await original_call_api(self, api, **data)
    
    try:
        # 检查是否是发送群消息的API
        if api == "send_msg":
            group_id = data.get("group_id")
            message = data.get("message", "")
            message_id = result.get("message_id") if isinstance(result, dict) else None
            
            reply_to_message_id = None
            for segment in message:
                if segment.type == 'reply':
                    # 如果是回复消息，获取回复的消息ID
                    reply_to_message_id = segment.data.get('id')

            if group_id:
                await record_bot_message(self, group_id, message, str(message_id) if message_id else None, reply_to_message_id)
                
    except Exception as e:
        logger.error(f"Hook记录机器人消息失败: {e}")
    
    return result

@driver.on_startup
async def hook_bot_methods():
    """在启动时Hook机器人方法"""
    global original_call_api
    
    # 等待一下确保Bot实例存在
    await asyncio.sleep(1)
    
    try:
        # Hook Bot 的 call_api 方法
        from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
        
        if original_call_api is None:
            original_call_api = OneBotV11Bot.call_api
            OneBotV11Bot.call_api = hooked_call_api
            logger.info("已Hook机器人call_api方法")
    except Exception as e:
        logger.error(f"Hook机器人方法失败: {e}")

def gen_message(message_chain: List[MessageSegment]) -> str:
    """生成纯文本内容"""
    return "".join(str(seg) for seg in message_chain if seg.type == 'text').strip()
            
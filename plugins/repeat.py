
from nonebot import on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.typing import T_State
from nonebot.plugin import PluginMetadata
from collections import defaultdict
from utils.rules import allow_group_rule
import random

__plugin_meta__ = PluginMetadata(
    name="应声虫",
    description="自动复读",
    usage="应声虫有20%的概率协战，但是如果你打一行字，我会有100%的概率复制你。",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

# 每个群的复读状态
# 格式: group_id -> {
#     "last_message": str,           # 上一条消息内容
#     "repeat_count": int,           # 当前消息已复读次数
#     "bot_repeated": bool,          # 机器人是否已复读过这条消息
#     "last_user_id": int           # 上一条消息的用户ID
# }
group_repeat_status = defaultdict(lambda: {
    "last_message": "",
    "repeat_count": 0,
    "bot_repeated": False,
    "last_user_id": None
})

def should_repeat(repeat_count: int) -> bool:
    """
    根据复读次数计算是否应该复读
    次数 > 2 时开始有概率复读
    次数 = 10 时概率达到 100%
    """
    if repeat_count <= 2:
        return False
    
    if repeat_count >= 10:
        return True
    
    # 线性增长概率：从次数3开始，每增加1次，概率增加约12.5%
    # 次数3: 12.5%, 次数4: 25%, ..., 次数9: 87.5%, 次数10: 100%
    probability = (repeat_count - 2) * 12.5
    logger.debug(f"复读次数: {repeat_count}, 复读概率: {probability}%")
    return random.random() * 100 < probability

def normalize_message(message_text: str) -> str:
    """
    标准化消息内容，用于比较是否为同一条消息
    移除首尾空白字符
    """
    return message_text.strip()

def is_valid_repeat_message(message_text: str) -> bool:
    """
    判断消息是否适合复读
    过滤掉一些不适合复读的消息类型
    """
    if not message_text or not message_text.strip():
        return False
    
    # 过滤掉太短的消息（如单个字符、表情等）
    if len(message_text.strip()) < 2:
        return False
    
    # 过滤掉以 / 开头的命令消息
    if message_text.strip().startswith('/'):
        return False
    
    # 过滤掉以 # 开头的标签消息
    if message_text.strip().startswith('#'):
        return False
    
    return True

# 启动时初始化
driver = get_driver()

@driver.on_startup
async def startup():
    logger.info("复读机插件已启动")

# 监听所有群消息
repeat_handler = on_message(rule=allow_group_rule, priority=20, block=False)

@repeat_handler.handle()
async def handle_repeat(bot: Bot, event: GroupMessageEvent, state: T_State):
    """处理群消息，判断是否需要复读"""
    try:
        group_id = event.group_id
        user_id = event.user_id
        current_message = normalize_message(event.get_plaintext())
        
        # 检查消息是否适合复读
        if not is_valid_repeat_message(current_message):
            return
        
        # 获取当前群的复读状态
        status = group_repeat_status[group_id]
        
        # 检查是否与上一条消息相同
        if current_message == status["last_message"]:
            # 如果是同一个用户连续发同样的消息，不计入复读
            if user_id == status["last_user_id"]:
                return
            
            # 增加复读次数
            status["repeat_count"] += 1
            status["last_user_id"] = user_id
            
            logger.debug(f"群 {group_id} 复读计数: {current_message[:20]}... x{status['repeat_count']}")
            
            # 判断是否应该复读
            if not status["bot_repeated"] and should_repeat(status["repeat_count"]):
                try:
                    # 机器人复读
                    await bot.send_group_msg(
                        group_id=group_id,
                        message=Message(current_message)
                    )
                    
                    # 标记已复读
                    status["bot_repeated"] = True
                    
                    logger.info(f"群 {group_id} 机器人复读: {current_message[:20]}... (复读次数: {status['repeat_count']})")
                    
                except Exception as e:
                    logger.error(f"发送复读消息失败: {e}")
        else:
            # 新的消息，重置状态
            status["last_message"] = current_message
            status["repeat_count"] = 1
            status["bot_repeated"] = False
            status["last_user_id"] = user_id
            
            logger.debug(f"群 {group_id} 新消息: {current_message[:20]}...")
    
    except Exception as e:
        logger.error(f"处理复读消息时发生错误: {e}")
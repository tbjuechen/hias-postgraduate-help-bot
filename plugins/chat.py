from nonebot import on_command, on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Event, Message, GroupMessageEvent, MessageSegment
from utils.rules import allow_group_rule
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.rule import to_me
from collections import defaultdict

from plugins.group_msg_collect import MessageRecorderAPI
from plugins.group_msg_collect import on_message_save
from utils.llm import llm_response
from chat.load import build_doc_base
from chat.client import Client


__plugin_meta__ = PluginMetadata(
    name="杭高问答",
    description="智能学院学姐问答助手，解答报考、复试、导师等相关问题",
    usage="/hias 或 /杭高问答 或 @机器人 <问题> - 等待学姐回答你的问题",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

# 指令 /hias
hias_cmd = on_command("hias", aliases={"杭高问答"}, priority=5)

# @机器人
hias_at = on_message(rule=to_me() & allow_group_rule, priority=10, block=False)

clients = defaultdict(lambda: Client(llm=llm_response))

@on_message_save
def handle_new_message(message):
    """处理新的消息，更新短期记忆"""
    message_dict = message.to_dict()
    group = message_dict.get("group_id")
    clients[group].new_message(str(message))

driver = get_driver()   

# @driver.on_startup
# async def startup():
#     """启动时构建知识库"""
#     logger.info("杭高问答插件已启动，正在构建知识库...")
#     await build_doc_base()
#     logger.info("知识库构建完成，杭高问答插件已就绪。")


async def handle_hias(bot: Bot, event: GroupMessageEvent):
    try:
        reply_chain = MessageRecorderAPI.get_reply_chain(event.message_id)
        # 获取回复的消息文本
        context = '\n'.join([str(seg) for seg in reply_chain])

        answer = await clients[event.group_id].chat(context)

        reply_msg = MessageSegment.reply(event.message_id) + answer

        return reply_msg
    
    except FinishedException:
        raise
    except Exception as e:
        return f"抱歉，发生错误了：{str(e)} 😢 请稍后再试或联系管理员。"

@hias_cmd.handle()
async def handle_hias_command(bot: Bot, event: GroupMessageEvent):
    await hias_cmd.finish(await handle_hias(bot, event))

@hias_at.handle()
async def handle_hias_at(bot: Bot, event: GroupMessageEvent):
    await hias_at.finish(await handle_hias(bot, event))
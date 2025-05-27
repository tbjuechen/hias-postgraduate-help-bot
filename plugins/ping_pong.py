from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, Message, GroupMessageEvent
from utils.rules import allow_group_rule

# 指令 /ping
ping = on_command("ping", aliases={"p"}, priority=5)

@ping.handle()
async def handle_ping(bot: Bot, event: Event):
    await ping.finish("pong")

# 监听群聊里@机器人并且消息是“ping”
at_ping = on_message(rule=allow_group_rule,priority=10)

@at_ping.handle()
async def handle_at_ping(bot: Bot, event: GroupMessageEvent):
    # 判断是否@了机器人
    if not event.is_tome():
        return
    # 消息内容
    msg_text = event.get_plaintext().strip().lower()
    print(f"Received text: '{msg_text}'")
    if "ping" in msg_text:
        await at_ping.finish("pong")
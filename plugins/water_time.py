from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.typing import T_State
from datetime import datetime
from collections import defaultdict
from utils.rules import allow_group_rule

import asyncio

# 维护统计数据的全局字典
# 默认格式: group_id -> user_id -> stats dict
group_stats = defaultdict(lambda: defaultdict(lambda: {
    "active_minutes": 0,
    "msg_count": 0,
    "last_speak_minute": None,
}))

def current_minute_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def current_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

state = {"current_date": current_date_str()}

# 每条群消息触发，更新统计
water_time = on_message(rule=allow_group_rule,priority=10)

@water_time.handle()
async def handle_water_time(event: GroupMessageEvent):
    global group_stats, state
    group_id = event.group_id
    user_id = event.user_id
    now_minute = current_minute_str()
    message_time = datetime.fromtimestamp(event.time).strftime("%Y-%m-%d")
    if message_time != state["current_date"]:
        # 如果消息时间不是今天，重置统计
        group_stats = defaultdict(lambda: defaultdict(lambda: {
            "active_minutes": 0,
            "msg_count": 0,
            "last_speak_minute": None,
        })) 
        state["current_date"] = message_time

    user_stats = group_stats[group_id][user_id]

    # 如果是当天新记录或者跨天，重置统计
    last_minute = user_stats["last_speak_minute"]
    if last_minute is None or not last_minute.startswith(current_date_str()):
        user_stats["active_minutes"] = 0
        user_stats["msg_count"] = 0
        user_stats["last_speak_minute"] = None

    # 增加消息数
    user_stats["msg_count"] += 1

    # 判断是否新增“水群分钟”
    if user_stats["last_speak_minute"] != now_minute:
        user_stats["active_minutes"] += 1
        user_stats["last_speak_minute"] = now_minute

# 添加一个查看当日水群统计的命令
stats_cmd = on_command("stats", rule=allow_group_rule, aliases={"水群统计"}, priority=5)

@stats_cmd.handle()
async def handle_stats(bot: Bot, event: GroupMessageEvent, state: T_State):
    group_id = event.group_id
    stats_data = group_stats.get(group_id)

    if not stats_data:
        await stats_cmd.finish("暂无统计数据")

    # 检查消息中有没有at成员
    at_user_ids = []
    for seg in event.message:
        if seg.type == "at" and seg.data.get("qq"):
            at_user_ids.append(int(seg.data["qq"]))

    if at_user_ids:
        # 如果有at，取第一个成员的统计
        user_id = at_user_ids[0]
        data = stats_data.get(user_id)
        if not data:
            await stats_cmd.finish(f"成员 {user_id} 无统计数据")
        name = await get_user_name(bot, group_id, user_id)
        msg = (f"{name} 的群活跃统计：\n"
               f"活跃分钟数：{data['active_minutes']}\n"
               f"消息数：{data['msg_count']}")
        await stats_cmd.finish(msg)
    else:
        # 没有at，则显示所有成员排名（最多10个）
        ranking = sorted(stats_data.items(), key=lambda x: x[1]["active_minutes"], reverse=True)
        msg_lines = ["今日群聊活跃度排名："]
        coros = [get_user_name(bot, group_id, uid) for uid, _ in ranking[:10]]
        names = await asyncio.gather(*coros)
        for (uid, data), name in zip(ranking[:10], names):
            msg_lines.append(f"{name} ：活跃 {data['active_minutes']} 分钟，消息数 {data['msg_count']}")
        await stats_cmd.finish("\n".join(msg_lines))

async def get_user_name(bot: Bot, group_id: int, user_id: int):
    try:
        member_info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=user_id,
            no_cache=True
        )
        return member_info.get("card") or member_info.get("nickname") or str(user_id)
    except:
        return str(user_id)
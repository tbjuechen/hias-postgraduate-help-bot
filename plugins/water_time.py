from nonebot import on_command, on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.typing import T_State
from datetime import datetime
from collections import defaultdict
from utils.rules import allow_group_rule

import json
import asyncio
from pathlib import Path

# 数据文件路径
DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "group_stats.json"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# 维护统计数据的全局字典
# 默认格式: group_id -> user_id -> stats dict
group_stats = defaultdict(lambda: defaultdict(lambda: {
    "active_minutes": 0,
    "msg_count": 0,
    "last_speak_minute": None,
    "total_msg_count": 0,
    "total_active_minutes": 0,
}))

def current_minute_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def current_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

state = {"current_date": current_date_str()}

def load_data():
    """从文件加载历史数据"""
    global group_stats
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 重构为defaultdict格式，只加载历史数据
                for group_id, users in data.items():
                    for user_id, stats in users.items():
                        group_stats[int(group_id)][int(user_id)].update({
                            "total_active_minutes": stats.get("total_active_minutes", 0),
                            "total_msg_count": stats.get("total_msg_count", 0)
                        })
                logger.info(f"已加载历史数据: {len(data)} 个群组")
    except Exception as e:
        logger.error(f"加载数据失败: {e}")

def save_data():
    """保存历史总数据到文件"""
    try:
        # 只保存历史总统计
        data = {}
        for group_id, users in group_stats.items():
            data[str(group_id)] = {}
            for user_id, stats in users.items():
                data[str(group_id)][str(user_id)] = {
                    "total_active_minutes": stats["total_active_minutes"],
                    "total_msg_count": stats["total_msg_count"]
                }
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"历史数据已保存到 {DATA_FILE}")
    except Exception as e:
        logger.error(f"保存数据失败: {e}")

async def periodic_save():
    """定期保存历史数据并更新总计"""
    while True:
        await asyncio.sleep(15 * 60)  # 15分钟
        save_data()

# 启动时加载数据
driver = get_driver()

@driver.on_startup
async def startup():
    load_data()
    # 启动定期保存任务
    asyncio.create_task(periodic_save())

@driver.on_shutdown
async def shutdown():
    save_data()

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
        # 如果消息时间不是今天，重置统计并更新历史总计
        save_data()
        load_data()
        # 重置当前日期
        state["current_date"] = message_time

    user_stats = group_stats[group_id][user_id]

    # # 如果是当天新记录或者跨天，重置统计
    last_minute = user_stats["last_speak_minute"]
    # if last_minute is None or not last_minute.startswith(current_date_str()):
    #     user_stats["active_minutes"] = 0
    #     user_stats["msg_count"] = 0
    #     user_stats["last_speak_minute"] = None

    # 增加消息数
    user_stats["msg_count"] += 1
    user_stats["total_msg_count"] += 1

    # 判断是否新增"水群分钟"
    if user_stats["last_speak_minute"] != now_minute:
        if last_minute is None:
            # 第一次发言，只算当前分钟
            user_stats["active_minutes"] += 1
            user_stats["total_active_minutes"] += 1
        else:
            old_active_minutes = user_stats["active_minutes"]
            # 计算时间间隔
            try:
                last_time = datetime.strptime(last_minute, "%Y-%m-%d %H:%M")
                current_time = datetime.strptime(now_minute, "%Y-%m-%d %H:%M")
                time_diff = (current_time - last_time).total_seconds() / 60
                
                if time_diff <= 3:
                    # 间隔不超过3分钟，这期间都在水群
                    minutes_to_add = int(time_diff)
                    user_stats["active_minutes"] += minutes_to_add
                    user_stats["total_active_minutes"] += minutes_to_add
                else:
                    # 间隔超过3分钟，只算当前分钟
                    user_stats["active_minutes"] += 1
                    user_stats["total_active_minutes"] += 1
            except:
                # 解析时间失败，只算当前分钟
                user_stats["active_minutes"] += 1
                user_stats["total_active_minutes"] += 1
            finally:
                try:
                    # 如果活跃分钟数达到整数小时，提醒成员
                    if old_active_minutes // 60 < user_stats["active_minutes"] // 60:
                        message ='[🤖提醒] ' + MessageSegment.at(user_id) + f' ⚠今日水群时间已到达{str(user_stats["active_minutes"] // 60)}小时'
                        await water_time.send(message)
                        logger.info(f"用户 {user_id} 在群 {group_id} 达到 {str(user_stats["active_minutes"] // 60)} 小时")
                except Exception as e:
                    logger.error(f"提醒用户水群时间失败: {e}")
        # 更新最后发言时间
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
        msg = (f"📊 {name} 的群活跃统计\n"
               f"━━━━━━━━━━━━━━━━━━━━━━\n"
               f"📅 今日数据：\n"
               f"  ⏰ 活跃时长：{data['active_minutes']} 分钟\n"
               f"  💬 发言次数：{data['msg_count']} 条\n"
               f"📈 历史总计：\n"
               f"  ⏰ 总活跃时长：{data['total_active_minutes']} 分钟\n"
               f"  💬 总发言次数：{data['total_msg_count']} 条")
        await stats_cmd.finish(msg)
    else:
        # 没有at，则显示所有成员排名（最多10个）
        ranking = sorted(stats_data.items(), key=lambda x: x[1]["active_minutes"], reverse=True)
        msg_lines = ["🏆 今日群聊活跃度排行榜", "━━━━━━━━━━━━━━━━━━━━━━"]
        coros = [get_user_name(bot, group_id, uid) for uid, _ in ranking[:10]]
        names = await asyncio.gather(*coros)
        for i, ((uid, data), name) in enumerate(zip(ranking[:10], names), 1):
            if i == 1:
                rank_emoji = "🥇"
            elif i == 2:
                rank_emoji = "🥈"
            elif i == 3:
                rank_emoji = "🥉"
            else:
                rank_emoji = f"{i}."

            msg_lines.append(f"{rank_emoji} {name}")
            msg_lines.append(f"   📅 今日：⏰{data['active_minutes']}分钟 💬{data['msg_count']}条")
            # msg_lines.append(f"   📈 总计：⏰{data['total_active_minutes']}分钟 💬{data['total_msg_count']}条")
            if i < len(ranking[:10]):
                msg_lines.append("   ────────────────────")

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
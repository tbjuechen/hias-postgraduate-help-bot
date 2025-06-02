from nonebot import on_command, on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.typing import T_State
from nonebot.plugin import PluginMetadata
from datetime import datetime, timedelta
from collections import defaultdict
from utils.rules import allow_group_rule

import json
import asyncio
from pathlib import Path

__plugin_meta__ = PluginMetadata(
    name="水群统计",
    description="统计群成员在水群中的活跃度",
    usage="/stats 或 /水群统计 - 查看当日水群排行榜\n/stats @成员 - 查看指定成员的水群统计",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

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

async def recover_today_stats():
    """从 group_msg_collect 数据库恢复当日水群统计"""
    try:
        from plugins.group_msg_collect import MessageRecorderAPI
        from utils.rules import allowed_groups
        
        logger.info("开始恢复当日水群统计...")
        
        # 获取今日开始时间
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        recovered_groups = 0
        recovered_users = 0
        
        # 遍历所有允许的群组
        for group_id_str in allowed_groups:
            try:
                group_id = int(group_id_str)
                
                # 获取该群今日的所有消息
                today_messages = MessageRecorderAPI.get_messages(
                    group_id=group_id,
                    start_time=today_start,
                    limit=10000,  # 获取足够多的消息
                    order_by="asc"
                )

                today_messages =[ msg.to_dict() for msg in today_messages]
                
                if not today_messages:
                    continue
                
                recovered_groups += 1
                group_users = set()
                
                # 按用户分组处理消息，排除机器人自己的消息
                user_messages = defaultdict(list)
                for msg in today_messages:
                    user_id = msg.get('user_id')
                    user_name = msg.get('user_name', '')
                    # 排除机器人消息（通过user_name判断）
                    if user_id and user_name != 'BOT':
                        user_messages[user_id].append(msg)
                
                # 为每个用户重新计算统计
                for user_id, messages in user_messages.items():
                    if not messages:
                        continue
                    
                    group_users.add(user_id)
                    user_stats = group_stats[group_id][user_id]
                    
                    # 重置当日统计
                    user_stats["active_minutes"] = 0
                    user_stats["msg_count"] = len(messages)
                    user_stats["last_speak_minute"] = None
                    
                    # 按时间顺序处理消息，计算活跃分钟数
                    active_minutes_set = set()
                    last_active_minute = None
                    
                    for msg in messages:
                        # 解析消息时间
                        created_at = msg.get('created_at')
                        if isinstance(created_at, str):
                            try:
                                msg_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                if msg_time.tzinfo:
                                    msg_time = msg_time.replace(tzinfo=None)
                            except:
                                continue
                        else:
                            continue
                        
                        current_minute = msg_time.strftime("%Y-%m-%d %H:%M")
                        
                        # 添加当前分钟到活跃分钟集合
                        active_minutes_set.add(current_minute)
                        
                        # 如果与上一条消息间隔不超过3分钟，填充中间的分钟
                        if last_active_minute:
                            try:
                                last_time = datetime.strptime(last_active_minute, "%Y-%m-%d %H:%M")
                                time_diff = (msg_time - last_time).total_seconds() / 60
                                
                                if 0 < time_diff <= 3:
                                    # 填充中间的分钟
                                    for i in range(1, int(time_diff)):
                                        fill_time = last_time + timedelta(minutes=i)
                                        fill_minute = fill_time.strftime("%Y-%m-%d %H:%M")
                                        active_minutes_set.add(fill_minute)
                            except:
                                pass
                        
                        last_active_minute = current_minute
                    
                    # 更新统计数据
                    user_stats["active_minutes"] = len(active_minutes_set)
                    user_stats["last_speak_minute"] = last_active_minute
                    
                    logger.debug(f"恢复用户 {user_id} 在群 {group_id} 的数据: {user_stats['msg_count']} 条消息, {user_stats['active_minutes']} 活跃分钟")
                
                recovered_users += len(group_users)
                logger.info(f"群 {group_id} 恢复完成: {len(group_users)} 个用户, {len(today_messages)} 条消息")
                
            except Exception as e:
                logger.error(f"恢复群 {group_id} 数据失败: {e}")
                continue
        
        logger.info(f"水群统计恢复完成: {recovered_groups} 个群组, {recovered_users} 个用户")
        
    except ImportError:
        logger.warning("未找到 group_msg_collect 插件，无法恢复当日统计")
    except Exception as e:
        logger.error(f"恢复当日水群统计失败: {e}")

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
    
    # 延迟执行恢复任务，确保其他插件已加载
    async def delayed_recovery():
        await asyncio.sleep(3)  # 等待3秒确保其他插件加载完成
        await recover_today_stats()
    
    asyncio.create_task(delayed_recovery())

@driver.on_shutdown
async def shutdown():
    save_data()

# 每条群消息触发，更新统计
water_time = on_message(rule=allow_group_rule, priority=10, block=False)

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
        group_stats = defaultdict(lambda: defaultdict(lambda: {
            "active_minutes": 0,
            "msg_count": 0,
            "last_speak_minute": None,
            "total_msg_count": 0,
            "total_active_minutes": 0,
        }))
        load_data()
        # 重置当前日期
        state["current_date"] = message_time
        # 重新恢复当日统计
        asyncio.create_task(recover_today_stats())

    user_stats = group_stats[group_id][user_id]

    # 记录旧的活跃分钟数用于提醒判断
    old_active_minutes = user_stats["active_minutes"]
    last_minute = user_stats["last_speak_minute"]

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
        
        # 更新最后发言时间
        user_stats["last_speak_minute"] = now_minute
        
        # 检查是否需要提醒
        try:
            if old_active_minutes // 60 < user_stats["active_minutes"] // 60:
                message = '[🤖提醒] ' + MessageSegment.at(user_id) + f' ⚠今日水群时间已到达{str(user_stats["active_minutes"] // 60)}小时'
                await water_time.send(message)
                logger.info(f"用户 {user_id} 在群 {group_id} 达到 {str(user_stats['active_minutes'] // 60)} 小时")
        except Exception as e:
            logger.error(f"提醒用户水群时间失败: {e}")

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
               f"━━━━━━━━━━━━━━━━━\n"
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
        msg_lines = ["🏆 今日群聊活跃度排行榜", "━━━━━━━━━━━━━━━━━"]
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
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.log import logger
from utils.rules import allow_group_rule
from datetime import datetime

__plugin_meta__ = PluginMetadata(
    name="提纯",
    description="自动清理长期不活跃的用户",
    usage="/clean 或 /提纯 - 清理群内长期不活跃的用户",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

inactive_members = []  # 暗杀名单
expired_time = 0

clean_cmd = on_command("clean", aliases={"提纯"}, priority=5, rule=allow_group_rule, block=True)

@clean_cmd.handle()
async def handle_clean_command(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    global inactive_members
    global expired_time
    inactive_members = []
    try:
        members = await bot.get_group_member_list(group_id=group_id)
        logger.debug(members)
        for member in members:
            # 检查成员的最后发言时间
            last_speak_time = member.get("last_sent_time", 0)
            if last_speak_time:
                # 将时间戳转换为 datetime 对象
                last_speak_dt = datetime.fromtimestamp(last_speak_time)
                # 计算当前时间与最后发言时间的差值
                time_diff = datetime.now() - last_speak_dt
                logger.debug(f"成员 {member['user_id']} 最后发言 {last_speak_dt}, 距今 {time_diff} 天")
                # 超过60天未发言
                if time_diff.days > 60:
                    # 等级小于2级且未改名
                    if int(member.get("level", 0)) <= 2 and member.get('card', '') == '':
                        logger.debug(f"成员 {member['user_id']} 等级 {member.get('level', 0)}，未改名，加入暗杀名单")
                        inactive_members.append({'id': member['user_id'], 'name': member.get('card', '') or member.get('nickname', '')})
        inactive_members_list = '\n'.join(map(lambda x: f"{x['id']}({x['name']})", inactive_members))
        expired_time = datetime.now()
        if len(inactive_members) == 0:
            await clean_cmd.finish("没有找到长期不活跃的用户。")
        else:
            await clean_cmd.finish(f'''查询成功，共找到 {len(inactive_members)} 个长期不活跃的用户。
暗杀名单：{inactive_members_list}
使用 /confirm_clean 确认清理，有效期1分钟。''')    
        
    except Exception as e:
        raise e  # debug only
    
confirm_clean_cmd = on_command("confirm_clean", aliases={"确认提纯"}, priority=5, rule=allow_group_rule, block=True)
@confirm_clean_cmd.handle()
async def handle_confirm_clean_command(bot: Bot, event: GroupMessageEvent):
    global inactive_members
    global expired_time
    if not inactive_members:
        await confirm_clean_cmd.finish("没有找到长期不活跃的用户。")
    # 检查是否在有效期内
    if (datetime.now() - expired_time).total_seconds() > 60:
        await confirm_clean_cmd.finish("清理请求已过期，请重新使用 /clean 命令查询。")
    
    group_id = event.group_id
    try:
        for member in inactive_members:
            user_id = member['id']
            # 发送踢人请求
            await bot.set_group_kick(group_id=group_id, user_id=user_id, reject_add_request=False)
            logger.info(f"已将用户 {user_id} ({member['name']}) 从群组 {group_id} 中移除。")
        await confirm_clean_cmd.finish(f"已成功清理 {len(inactive_members)} 个长期不活跃的用户。")
    except FinishedException as e:
        raise e
    
    except Exception as e:
        logger.error(f"清理过程中发生错误: {e}")
        await confirm_clean_cmd.finish(f"清理过程中发生错误{e}，请稍后再试。")
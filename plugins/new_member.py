from nonebot import on_request, on_notice, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent, GroupIncreaseNoticeEvent, MessageSegment
from nonebot.plugin import PluginMetadata
from utils.rules import allow_group_rule
import os
import json
import asyncio
from collections import defaultdict
from datetime import datetime

__plugin_meta__ = PluginMetadata(
    name="加群申请处理",
    description="自动处理加群申请，通过含指定关键字的申请并欢迎新成员",
    usage="自动运行，无需手动操作",
    supported_adapters={"~onebot.v11"},
)

# 从环境变量读取欢迎消息
WELCOME_MESSAGE = os.getenv('GROUP_WELCOME_MESSAGE', 
    """🎉 欢迎新同学加入杭高院考研群！

📚 这里是国科大杭州高等研究院智能学院的考研交流群
💡 有任何关于报考、复试、导师等问题都可以@机器人咨询
📋 建议先查看群文件中的报考指南和FAQ
🤝 祝愿大家都能顺利上岸！

快来介绍一下自己吧～""")

keywords = ['b站', 'bilibili', 'B站', '小红书', 'xhs', '知乎', '同学', '学姐', '学长', '考研',
            '引流', '铁柱', '群', '公众号', '微信', 'dy', '抖音', '经验贴', '宣讲']
logger.info(f"加群申请关键词: {keywords}")

# 新成员暂存列表：群ID -> [(用户ID, 用户名, 加入时间)]
pending_welcomes = defaultdict(list)

# 获取驱动器用于定时任务
driver = get_driver()

async def send_batch_welcome():
    """批量发送欢迎消息的定时任务"""
    while True:
        try:
            await asyncio.sleep(60)  # 每60秒执行一次
            
            if not pending_welcomes:
                continue
            
            # 获取当前所有Bot实例
            from nonebot import get_bots
            bots = get_bots()
            
            if not bots:
                logger.warning("没有可用的Bot实例")
                continue
            
            # 使用第一个可用的Bot
            bot = list(bots.values())[0]
            
            # 处理每个群的新成员
            groups_to_clear = []
            for group_id, members in pending_welcomes.items():
                if not members:
                    continue
                    
                try:
                    # 检查群组是否在允许列表中
                    from utils.rules import allowed_groups
                    if str(group_id) not in allowed_groups:
                        groups_to_clear.append(group_id)
                        continue
                    
                    # 构造批量欢迎消息
                    if len(members) == 1:
                        # 单个成员
                        user_id, username, join_time = members[0]
                        welcome_msg = MessageSegment.at(user_id) + f" {username}\n" + WELCOME_MESSAGE
                    else:
                        # 多个成员
                        at_segments = []
                        names = []
                        for user_id, username, join_time in members:
                            at_segments.append(MessageSegment.at(user_id))
                            names.append(username)
                        
                        # 构造消息：多个@后面跟欢迎词
                        welcome_msg = "".join([str(seg) + " " for seg in at_segments]) + f"\n🎉 欢迎 {', '.join(names)} 等 {len(members)} 位新同学加入杭高院考研群！\n\n" + WELCOME_MESSAGE
                    
                    # 发送欢迎消息
                    await bot.send_group_msg(
                        group_id=group_id,
                        message=welcome_msg
                    )
                    
                    logger.info(f"已向群 {group_id} 的 {len(members)} 位新成员发送批量欢迎消息")
                    groups_to_clear.append(group_id)
                    
                except Exception as e:
                    logger.error(f"发送群 {group_id} 批量欢迎消息失败: {e}")
                    groups_to_clear.append(group_id)
            
            # 清空已处理的群组
            for group_id in groups_to_clear:
                pending_welcomes[group_id].clear()
                
        except Exception as e:
            logger.error(f"批量欢迎任务执行失败: {e}")

@driver.on_startup
async def start_welcome_task():
    """启动时创建批量欢迎任务"""
    asyncio.create_task(send_batch_welcome())
    logger.info("批量欢迎任务已启动")

# 处理加群申请
group_request_handler = on_request(priority=5)

@group_request_handler.handle()
async def handle_group_request(bot: Bot, event: GroupRequestEvent):
    """处理加群申请"""
    try:
        # 检查是否为加群申请
        if event.request_type != "group" or event.sub_type != "add":
            return
        
        # 检查群组是否在允许列表中
        from utils.rules import allowed_groups
        if str(event.group_id) not in allowed_groups:
            logger.info(f"群 {event.group_id} 不在允许列表中，跳过处理")
            return
        
        # 获取申请信息
        user_id = event.user_id
        group_id = event.group_id
        comment = event.comment or ""
        
        logger.info(f"收到加群申请: 群{group_id}, 用户{user_id}, 申请信息: {comment}")
        
        # 检查申请信息是否包含关键词
        should_approve = False
        matched_keyword = None
        
        for keyword in keywords:
            if keyword.lower() in comment.lower():
                should_approve = True
                matched_keyword = keyword
                break
        
        if should_approve:
            # 自动同意申请
            try:
                await bot.set_group_add_request(
                    flag=event.flag,
                    sub_type=event.sub_type,
                    approve=True,
                    reason=""
                )
                logger.info(f"已自动同意用户 {user_id} 的加群申请 (匹配关键词: {matched_keyword})")
                
                # 可选：向管理员发送通知
                # try:
                #     # 获取群信息和用户信息
                #     group_info = await bot.get_group_info(group_id=group_id)
                #     user_info = await bot.get_stranger_info(user_id=user_id)
                    
                #     admin_notice = (f"🤖 自动同意加群申请\n"
                #                   f"群聊: {group_info.get('group_name', group_id)}\n"
                #                   f"用户: {user_info.get('nickname', user_id)}({user_id})\n"
                #                   f"申请信息: {comment}\n"
                #                   f"匹配关键词: {matched_keyword}")
                    
                #     # 发送给管理员(这里可以配置管理员QQ)
                #     admin_qq = os.getenv('ADMIN_QQ')
                #     if admin_qq:
                #         await bot.send_private_msg(user_id=int(admin_qq), message=admin_notice)
                        
                # except Exception as e:
                #     logger.warning(f"发送管理员通知失败: {e}")
                    
            except Exception as e:
                logger.error(f"同意加群申请失败: {e}")
        else:
            logger.info(f"用户 {user_id} 的加群申请不包含关键词，未自动处理")
            
    except Exception as e:
        logger.error(f"处理加群申请时发生错误: {e}")

# 处理新成员入群通知
group_increase_handler = on_notice(priority=5)

@group_increase_handler.handle()
async def handle_group_increase(bot: Bot, event: GroupIncreaseNoticeEvent):
    """处理新成员入群事件，将成员添加到待欢迎列表"""
    try:
        # 检查是否为成员增加事件
        if event.notice_type != "group_increase":
            return
            
        # 检查群组是否在允许列表中
        from utils.rules import allowed_groups
        if str(event.group_id) not in allowed_groups:
            return
        
        # 检查是否为机器人自己入群
        if event.user_id == int(bot.self_id):
            logger.info(f"机器人加入群 {event.group_id}")
            return
        
        user_id = event.user_id
        group_id = event.group_id
        
        logger.info(f"新成员 {user_id} 加入群 {group_id}，已添加到待欢迎列表")
        
        # 获取用户信息
        try:
            member_info = await bot.get_group_member_info(
                group_id=group_id,
                user_id=user_id
            )
            username = member_info.get("card") or member_info.get("nickname") or str(user_id)
        except:
            username = str(user_id)
        
        # 添加到待欢迎列表
        join_time = datetime.now()
        pending_welcomes[group_id].append((user_id, username, join_time))
        
        logger.info(f"新成员 {username}({user_id}) 已添加到群 {group_id} 的待欢迎列表，当前列表长度: {len(pending_welcomes[group_id])}")
        
    except Exception as e:
        logger.error(f"处理新成员入群时发生错误: {e}")
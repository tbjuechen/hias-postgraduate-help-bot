from nonebot import on_request, on_notice, logger
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent, GroupIncreaseNoticeEvent, MessageSegment
from nonebot.plugin import PluginMetadata
from utils.rules import allow_group_rule
import os
import json

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

keywords = ['b站', 'bilibili', 'B站', '小红书', 'xhs', '知乎', '同学', '学姐', '学长', '考研'\
            , '引流', '铁柱', '群', '公众号', '微信', 'dy', '抖音', '经验贴', '宣讲']
logger.info(f"加群申请关键词: {keywords}")

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
    """处理新成员入群事件"""
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
        
        logger.info(f"新成员 {user_id} 加入群 {group_id}")
        
        # 获取用户信息
        try:
            member_info = await bot.get_group_member_info(
                group_id=group_id,
                user_id=user_id
            )
            username = member_info.get("card") or member_info.get("nickname") or str(user_id)
        except:
            username = str(user_id)
        
        # 构造欢迎消息
        welcome_msg = MessageSegment.at(user_id) + f" {username}\n" + WELCOME_MESSAGE
        
        # 发送欢迎消息
        await bot.send_group_msg(
            group_id=group_id,
            message=welcome_msg
        )
        
        logger.info(f"已向新成员 {username}({user_id}) 发送欢迎消息")
        
    except Exception as e:
        logger.error(f"处理新成员入群时发生错误: {e}")
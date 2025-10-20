from nonebot import on_command, on_message, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Event, Message, PrivateMessageEvent, MessageSegment
from utils.rules import allow_group_rule
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.rule import to_me
from collections import defaultdict


from .model import check_binding_conflict, create_binding

__plugin_meta__ = PluginMetadata(
    name="报考信息校验",
    description="通过私聊发送报考截图，机器人会自动校验信息并将校验通过的用户拉入报考群",
    usage="私聊机器人发送报考截图",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

chat_recorder = on_message(priority=10, block=False)

@chat_recorder.handle()
async def handle_sign_check(bot: Bot, event: PrivateMessageEvent):
    message = event.get_message()
    image_segments = message["image"]
    if not image_segments:
        # 消息中没有图片，不处理 (函数在此结束)
        logger.debug(f"用户 {event.user_id} 发送的不是图片，已忽略。")
        return
    
    try:
        first_image: MessageSegment = image_segments[0]
        image_url = first_image.data.get("url")

        if not image_url:
            logger.warning(f"用户 {event.user_id} 发送了图片，但无法获取URL。")
            await chat_recorder.send("无法解析你发送的图片，请尝试重新发送。")
            return

    except Exception as e:
        logger.error(f"提取图片 URL 时出错: {e}")
        await chat_recorder.send("提取图片时发生错误，请重试。")
        return
    
    try:
        # await 会等待 ocr_check 函数执行完毕
        result, name = await ocr_check(image_url)
        
    except Exception as e:
        # 捕获 ocr_check 内部可能发生的未知错误
        logger.error(f"ocr_check 函数执行失败: {e}")
        await chat_recorder.send("图片校验功能内部错误，请联系管理员。")

    if result:
        check_result = check_binding_conflict(event.user_id, name)
        if check_result:
            chat_recorder.send(f"校验失败：{check_result}")
            return
        
        creation_success = create_binding(event.user_id, name)
        if creation_success:
            await chat_recorder.send(f"校验成功！姓名 {name} 已绑定到你的 QQ 账号。你已被拉入报考群，请注意查收邀请。")
            result = await bot.call_api("ArkShareGroup", group_id='665145078')
            card_message = MessageSegment.json(data=result)
            try:
                await bot.send_private_msg(
                    user_id=event.user_id,
                    message=card_message
                )
                logger.info(f"已成功向 {event.user_id} 发送群卡片。")
            except Exception as e:
                logger.error(f"发送群卡片失败: {e}")
        else:
            await chat_recorder.send("校验失败：创建绑定时发生错误，请稍后重试或联系管理员。")
    
from pathlib import Path
from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, MessageSegment
from nonebot.plugin import PluginMetadata
import aiohttp
import aiofiles

from .ocr import OCRValidationError, QPSLimitError, ocr_check
from .model import check_binding_conflict, create_binding

DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "sign_check_images"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

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
        logger.info(f"用户 {event.user_id} 发送了图片，URL: {image_url}")

        if not image_url:
            logger.warning(f"用户 {event.user_id} 发送了图片，但无法获取 URL。")
            await chat_recorder.send("无法解析你发送的图片 URL，请尝试重新发送。")
            return

        image_name = first_image.data.get("file")
        image_path = IMAGES_DIR / f"{image_name}"
        # 检查该图片是否已存在，避免重复保存
        if image_path.exists():
            logger.info(f"图片已存在，跳过保存: {image_path}")
            await chat_recorder.send("你发送的图片已被处理过，请勿重复发送相同图片。")
            return
    except Exception as e:
        logger.error(f"提取图片时出错: {e}")
        await chat_recorder.send("提取图片时发生错误，请重试。")
        return

    try:
        # await 会等待 ocr_check 函数执行完毕
        result, signup_id = await ocr_check(image_url)
    except QPSLimitError:
        # 捕获自定义的 OCR 请求过于频繁错误
        logger.info(f"OCR 请求过于频繁，已要求用户 {event.user_id} 稍后重试。")
        await chat_recorder.send("该功能使用人数过多，请稍后重试。")
        return
    except OCRValidationError as e:
        # 捕获自定义的 OCR 校验错误
        logger.info(f"OCR 校验失败: {e}")
        await chat_recorder.send(f"图片校验失败：{e}")
        return
    except Exception as e:
        # 捕获 ocr_check 内部可能发生的未知错误
        logger.error(f"ocr_check 函数执行失败: {e}")
        await chat_recorder.send("图片校验功能内部错误，请联系管理员。")

    if result:
        check_result = check_binding_conflict(event.user_id, signup_id)
        if check_result:
            await chat_recorder.send(f"校验失败：{check_result}")
            return
        
        creation_success = create_binding(event.user_id, signup_id)
        if creation_success:
            await chat_recorder.send(f"校验成功！报名号 {signup_id} 已绑定到你的 QQ 账号。你已被拉入报考群，请注意查收邀请。")
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

        # 下载图片
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                content = await response.read()

        # 保存图片到本地
        async with aiofiles.open(image_path, "wb") as f:
            await f.write(content)

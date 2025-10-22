from nonebot import on_command, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.log import logger
from utils.rules import allow_group_rule

import jmcomic

import os
from pathlib import Path
from utils.http_server import start_static_server, stop_static_server, get_file_url

__plugin_meta__ = PluginMetadata(
    name="JM 漫画",
    description="提供 JM 漫画相关功能",
    usage="/jm [漫画id] - 下载指定 JM 漫画",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

jm_cmd = on_command("jm", priority=5, block=True)
option = jmcomic.create_option_by_file('./jm_option.yml')

ROOT_DIR = Path(os.getcwd()) / "data" / "jm" / "pdf"
PUBLIC_SERVER_IP = os.getenv("PUBLIC_SERVER_IP", "0.0.0.0")

driver = get_driver()

@driver.on_startup
async def start_file_server():
    """NoneBot 启动时，启动异步文件服务器"""
    try:
        # 确保下载目录存在
        ROOT_DIR.mkdir(parents=True, exist_ok=True)
        # 启动 aiohttp 服务器，共享 ROOT_DIR
        await start_static_server(ROOT_DIR)
    except Exception as e:
        logger.error(f"启动文件服务器失败: {e}")
        # 如果启动失败，可以选择退出或继续运行（但文件上传功能会受影响）
        
@driver.on_shutdown
async def stop_file_server():
    """NoneBot 关闭时，关闭异步文件服务器"""
    await stop_static_server()

@jm_cmd.handle()
async def handle_jm(bot: Bot, event: GroupMessageEvent):
    if event.group_id != 2150889802:
        await jm_cmd.finish("本命令仅限指定群使用。")
    args = str(event.get_message()).strip().split(' ')[1]
    if not args:
        await jm_cmd.finish("请提供漫画ID，例如：/jm 12345")
    
    logger.debug(f"Received JM command with args: {args}")
    comic_id = args
    try:
        option.download_album(int(comic_id))
        logger.info(f"Successfully downloaded comic with ID: {comic_id}")

        pdf_file_name = f"{comic_id}.pdf"
        pdf_path = ROOT_DIR / pdf_file_name

        if not pdf_path.exists():
            await jm_cmd.finish("下载完成，但未找到对应的 PDF 文件。")
        
        public_file_url = get_file_url(pdf_file_name, PUBLIC_SERVER_IP)

        await bot.upload_group_file(
            group_id=event.group_id,
            file=public_file_url, # 使用公网 URL
            name=pdf_file_name, 
        )
        
        raw_message_id = event.message_id
        quote_msg_segment = MessageSegment.reply(raw_message_id)
        full_message = quote_msg_segment + MessageSegment.text("文件已成功上传到群文件。请在群文件内查看。")
        await bot.send(
            event=event, 
            message=full_message
        )
    
    except Exception as e:
        await jm_cmd.finish(f"获取漫画信息时出错：{str(e)}")

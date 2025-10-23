import asyncio
import os
from pathlib import Path

from nonebot import on_command, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment, Message
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.utils import run_sync  # 导入 run_sync

import jmcomic

# from utils.http_server import start_static_server, stop_static_server, get_file_url # 你的导入
# 假设你的 http_server 模块是可用的
from utils.http_server import start_static_server, stop_static_server, get_file_url

__plugin_meta__ = PluginMetadata(
    name="JM 漫画",
    description="提供 JM 漫画相关功能",
    usage="/jm [漫画id] - 下载指定 JM 漫画",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

jm_cmd = on_command("jm", priority=5, block=True)
option = jmcomic.create_option_by_file('./jm_option.yml')

ROOT_DIR = Path(os.getcwd()) / "data" / "jm" / "download"
PUBLIC_SERVER_IP = os.getenv("PUBLIC_SERVER_IP", "0.0.0.0")

# # (可选) 定义你想识别为图片的后缀名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

driver = get_driver()

@driver.on_startup
async def start_file_server():
    """NoneBot 启动时，启动异步文件服务器"""
    try:
        ROOT_DIR.mkdir(parents=True, exist_ok=True)
        await start_static_server(ROOT_DIR)
    except Exception as e:
        logger.error(f"启动文件服务器失败: {e}")
        
@driver.on_shutdown
async def stop_file_server():
    """NoneBot 关闭时，关闭异步文件服务器"""
    await stop_static_server()

@jm_cmd.handle()
async def handle_jm(bot: Bot, event: GroupMessageEvent):
    if event.group_id != 2150889802:
        await jm_cmd.finish("本命令仅限指定群使用。")
    
    args_list = str(event.get_message()).strip().split()
    if len(args_list) < 2:
        await jm_cmd.finish("请提供漫画ID，例如：/jmtest 12345")
    
    comic_id = args_list[1]
    logger.debug(f"Received JM command with comic_id: {comic_id}")

    comic_folder_path = ROOT_DIR / comic_id
    
    try:
        # --- 1. 异步下载漫画 ---
        await jm_cmd.send(f"开始下载漫画 {comic_id}，这可能需要几分钟，请稍候...")
        
        @run_sync
        def _download_comic_sync():
            option.download_album(int(comic_id))
        
        await _download_comic_sync()
        logger.info(f"Successfully downloaded comic with ID: {comic_id}")

        # --- 2. 检查下载目录是否存在 ---
        if not comic_folder_path.is_dir():
            await jm_cmd.finish(f"下载完成，但未找到对应的漫画目录: {comic_folder_path.resolve()}")

        # --- 3. 获取 Bot 信息 ---
        bot_info = await bot.get_login_info()
        bot_self_id = bot_info["user_id"]
        bot_nickname = bot_info["nickname"]
        
        forward_nodes = []

        # --- 4. 遍历文件夹并构建图片节点 (这部分不变) ---
        logger.info(f"开始遍历 {comic_folder_path} 中的图片...")
        image_files = sorted(
            [p for p in comic_folder_path.iterdir() 
             if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
        )

        if not image_files:
            await jm_cmd.finish(f"漫画 {comic_id} 目录中未找到任何图片文件。")

        for img_path in image_files:
            try:
                relative_path = img_path.relative_to(ROOT_DIR).as_posix()
                image_url = get_file_url(relative_path, PUBLIC_SERVER_IP)
                content = Message(MessageSegment.image(image_url))
                
                node = MessageSegment.node_custom(
                    user_id=bot_self_id,
                    nickname=bot_nickname,
                    content=content
                )
                forward_nodes.append(node)
                
            except Exception as e:
                logger.error(f"处理图片 {img_path} 失败: {e}")
                forward_nodes.append(MessageSegment.node_custom(
                    user_id=bot_self_id,
                    nickname="系统错误",
                    content=Message(f"加载图片 {img_path.name} 失败")
                ))

        if not forward_nodes:
            await jm_cmd.finish("未能成功构造任何消息节点。")

        # --- 5. 【关键修改】分块发送合并转发消息 ---
        
        # 定义每个分块的大小
        CHUNK_SIZE = 20
        
        total_chunks = (len(forward_nodes) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for i in range(total_chunks):
            # 计算当前块的起始和结束索引
            start_index = i * CHUNK_SIZE
            end_index = (i + 1) * CHUNK_SIZE
            
            # 从总列表中切片出当前块
            current_chunk_nodes = forward_nodes[start_index:end_index]
            
            logger.info(f"正在发送 漫画 {comic_id} - (分块 {i+1}/{total_chunks})...")
            
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=current_chunk_nodes  # 传入当前块的节点列表
            )
            
            # !!! 关键：在两次发送之间加入延时，避免触发风控 !!!
            await asyncio.sleep(2) # 休息 2 秒

        # --- 6. 修改最终回复 ---
        raw_message_id = event.message_id
        quote_msg_segment = MessageSegment.reply(raw_message_id)
        full_message = quote_msg_segment + MessageSegment.text(
            f"漫画 {comic_id} (共 {len(forward_nodes)}P, 分 {total_chunks} 条消息) 已发送完毕。"
        )
        await bot.send(
            event=event, 
            message=full_message
        )
    
    except Exception as e:
        logger.error(f"处理漫画 {comic_id} 时出错: {e}")
        await jm_cmd.finish(f"获取或发送漫画 {comic_id} 时出错：{str(e)}")
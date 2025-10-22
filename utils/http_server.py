import os
import asyncio
from aiohttp import web
from pathlib import Path
from typing import Optional

# 存储全局 Web 应用引用和 Runner 引用，以便在 shutdown 时关闭
global_runner: Optional[web.AppRunner] = None
global_site: Optional[web.TCPSite] = None
global_app: Optional[web.Application] = None

# --- 配置 ---
HOST = "0.0.0.0" # 绑定到所有接口，允许外部访问
PORT = 8088      # 稳定的端口号

async def start_static_server(share_dir: Path):
    """
    异步启动 aiohttp Web 服务器，共享指定目录。
    """
    global global_runner, global_site, global_app
    
    if global_runner:
        print("警告：文件服务器已在运行中。")
        return

    if not share_dir.is_dir():
        raise FileNotFoundError(f"共享目录不存在: {share_dir}")

    # 1. 创建 Web 应用
    app = web.Application()
    
    # 2. 添加静态文件路由：将所有对 /static/* 的请求映射到 share_dir
    # 根路径 / 映射到 share_dir 下的文件
    app.router.add_static('/', path=share_dir, show_index=True)
    
    # 3. 创建 Runner 和 Site
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    
    # 4. 存储全局引用
    global_runner = runner
    global_site = site
    global_app = app
    
    print("-" * 50)
    print(f"🎉 aiohttp 文件服务器已启动！")
    print(f"💻 监听地址: http://{HOST}:{PORT}")
    print(f"📂 共享目录: {share_dir.resolve()}")
    print("-" * 50)


async def stop_static_server():
    """
    异步停止 aiohttp Web 服务器。
    """
    global global_runner, global_site, global_app
    
    if global_runner is None:
        return

    print("✋ 正在关闭 aiohttp 文件服务器...")
    try:
        # 1. 停止 Site 监听
        await global_site.stop()
        # 2. 清理 Runner 资源
        await global_runner.cleanup()
        
        print("✅ aiohttp 文件服务器已成功关闭。")
    except Exception as e:
        print(f"警告：关闭 aiohttp 服务器时发生错误: {e}")
    finally:
        global_runner = None
        global_site = None
        global_app = None

# 辅助函数：根据文件名和配置生成 URL
def get_file_url(file_name: str, public_ip: str) -> str:
    """构造远程服务器上文件的公共 URL"""
    return f"http://{public_ip}:{PORT}/{file_name}"
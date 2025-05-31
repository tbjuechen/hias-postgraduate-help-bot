from nonebot import get_driver, init
from nonebot.adapters.onebot.v11 import Adapter
import os
from dotenv import load_dotenv
import nonebot

load_dotenv()  # 如果用 .env 文件配置环境变量

init()
driver = get_driver()
driver.register_adapter(Adapter)
nonebot.load_plugin("nonebot_plugin_resolver2")
nonebot.load_plugin("nonebot_plugin_status")
nonebot.load_plugin("nonebot_plugin_wordcloud")
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    driver.run()
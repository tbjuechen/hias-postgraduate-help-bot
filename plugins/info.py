
from nonebot import on_command, get_driver
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from utils.rules import allow_group_rule
from pathlib import Path
import toml

__plugin_meta__ = PluginMetadata(
    name="项目信息",
    description="显示机器人项目基本信息",
    usage="/info 或 /版本 - 查看项目信息",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

# 项目信息缓存
project_info = None

def load_project_info():
    """加载 pyproject.toml 项目信息"""
    global project_info
    
    try:
        # 查找 pyproject.toml 文件
        pyproject_path = Path("pyproject.toml")
        if not pyproject_path.exists():
            # 尝试在上级目录查找
            pyproject_path = Path("../pyproject.toml")
            if not pyproject_path.exists():
                return None
        
        # 读取 pyproject.toml 文件
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            data = toml.load(f)
        
        # 提取项目信息
        project_section = data.get('project', {})
        
        project_info = {
            'name': project_section.get('name', '未知项目'),
            'version': project_section.get('version', '未知版本'),
            'description': project_section.get('description', '无描述')
        }
        
        return project_info
        
    except Exception as e:
        return None

# 初始化时加载项目信息
driver = get_driver()

@driver.on_startup
async def load_info():
    """启动时加载项目信息"""
    load_project_info()

info_cmd = on_command("info", rule=allow_group_rule, aliases={"版本", "信息"}, priority=5, block=True)

@info_cmd.handle()
async def handle_info(bot: Bot, event: MessageEvent):
    """处理info命令"""
    try:
        # 获取项目信息
        if not project_info:
            load_project_info()
        
        if project_info:
            # 显示项目基本信息
            info_text = f"""🤖 {project_info['name']}
📦 版本: {project_info['version']}
📖 描述: {project_info['description']}"""
        else:
            info_text = """⚠️ 无法读取项目配置文件"""
        
        await info_cmd.finish(info_text)
    
    except FinishedException:
        return
    except Exception as e:
        await info_cmd.finish(f"❌ 获取项目信息失败: {str(e)}")

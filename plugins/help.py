from nonebot import get_loaded_plugins, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.log import logger
from utils.rules import allow_group_rule

__plugin_meta__ = PluginMetadata(
    name="帮助系统",
    description="查看机器人功能和插件使用方法",
    usage="/help 或 /帮助 - 查看所有插件\n/help <插件名> - 查看具体插件用法",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

# 需要过滤的插件（三方插件和系统插件）
FILTERED_PLUGINS = {
    "uniseg",
    "group_msg_collect",  # 内部数据收集插件，用户不需要直接使用
    "new_member",  # 新成员欢迎插件
}

help_cmd = on_command("help", rule=allow_group_rule, aliases={"帮助"}, priority=1)

@help_cmd.handle()
async def handle_help(bot: Bot, event: MessageEvent):
    """处理帮助命令"""
    try:
        # 获取命令参数
        args = str(event.get_message()).strip()[5:].strip()
        logger.debug(f"收到帮助查询：{args}")
        
        if not args:
            # 没有参数，显示所有插件列表
            await show_all_plugins(event)
        else:
            # 有参数，显示特定插件详情
            await show_plugin_detail(event, args)

    except FinishedException:
        return      
    except Exception as e:
        await help_cmd.finish(f"❌ 获取帮助信息失败: {str(e)}")

async def show_all_plugins(event: MessageEvent):
    """显示所有插件的帮助信息"""
    help_lines = ["🤖 杭高院考研群机器人", '']
    
    # 获取过滤后的插件
    filtered_plugins = []
    for plugin in get_loaded_plugins():
        # 过滤系统插件和三方插件
        if plugin.name in FILTERED_PLUGINS:
            continue
        if plugin.name.startswith("nonebot_plugin_"):
            continue
            
        # 只显示有元数据的插件
        if plugin.metadata:
            filtered_plugins.append(plugin)
    
    if not filtered_plugins:
        await help_cmd.finish("❌ 暂无可用插件")
    
    # 按插件名称排序
    filtered_plugins.sort(key=lambda p: p.metadata.name)
    
    # 添加插件信息
    for i, plugin in enumerate(filtered_plugins, 1):
        logger.debug(f"插件 {i}: {plugin.name} - {plugin.metadata.name if plugin.metadata else '无元数据'}")
        meta = plugin.metadata
        help_lines.append(f"  📦 {meta.name}")
        help_lines.append(f"  📖 {meta.description}")
        help_lines.append('')
    
    # help_lines.append("")
    help_lines.append("💡 使用方法:")
    help_lines.append("   /help <插件名> - 查看具体用法")
    help_lines.append("   例如: /help ping")
    
    await help_cmd.finish("\n".join(help_lines))

async def show_plugin_detail(event: MessageEvent, plugin_name: str):
    """显示特定插件的详细信息"""
    # 查找插件（支持模糊匹配）
    target_plugin = None
    
    for plugin in get_loaded_plugins():
        if plugin.name in FILTERED_PLUGINS:
            continue
            
        if not plugin.metadata:
            continue
            
        meta = plugin.metadata
        # 精确匹配或模糊匹配
        if (plugin_name.lower() == meta.name.lower() or 
            plugin_name.lower() in meta.name.lower() or
            plugin_name.lower() == plugin.name.lower()):
            target_plugin = plugin
            break
    
    if not target_plugin:
        # 提供可用插件建议
        available_plugins = []
        for plugin in get_loaded_plugins():
            if plugin.name not in FILTERED_PLUGINS and not plugin.name.startswith("nonebot_plugin_") and plugin.metadata:
                available_plugins.append(plugin.metadata.name)
        
        suggestion = ""
        if available_plugins:
            suggestion = f"\n\n💡 可用插件: {', '.join(available_plugins[:5])}"
            if len(available_plugins) > 5:
                suggestion += f" 等{len(available_plugins)}个插件"
        
        await help_cmd.finish(f"❌ 未找到插件 '{plugin_name}'{suggestion}")
    
    # 显示插件详细信息
    meta = target_plugin.metadata
    detail_lines = [
        f"📦 {meta.name}",
    ]
    
    if meta.description:
        detail_lines.append(f"📖 功能描述:")
        detail_lines.append(f"   {meta.description}")
        detail_lines.append("")
    
    if meta.usage:
        detail_lines.append(f"📝 使用方法:")
        # 处理多行用法说明
        usage_lines = meta.usage.split('\n')
        for line in usage_lines:
            if line.strip():
                detail_lines.append(f"   {line.strip()}")
        detail_lines.append("")
    
    # 添加支持的适配器信息（如果有）
    # if hasattr(meta, 'supported_adapters') and meta.supported_adapters:
    #     adapters = ', '.join(meta.supported_adapters)
    #     detail_lines.append(f"🔌 支持适配器: {adapters}")
    
    # 添加返回提示
    # detail_lines.append("")
    detail_lines.append("💡 使用 /help 查看所有插件")
    
    await help_cmd.finish("\n".join(detail_lines))
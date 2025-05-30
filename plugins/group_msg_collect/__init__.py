from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="消息记录器",
    description="记录群聊消息到数据库，提供查询接口",
    usage="自动记录所有群消息，提供查询API",
    supported_adapters={"~onebot.v11"},
)

from .model import MessageRecord
from .query import MessageRecorderAPI

__all__ = ["MessageRecorderAPI", "MessageRecord"]

from . import plugin
from .plugin import message_recorder
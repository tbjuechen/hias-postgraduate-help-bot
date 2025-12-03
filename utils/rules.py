import json
import os
from pathlib import Path
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent
from nonebot import logger

import ast

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_allowed_groups():
    value = os.getenv('allowed_groups', "")
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []

allowed_groups = load_allowed_groups()

async def only_allowed_group(event: GroupMessageEvent) -> bool:
    return str(event.group_id) in allowed_groups

allow_group_rule = Rule(only_allowed_group)

# 仅允许群主和管理员调用的 Rule
async def _is_group_owner_or_admin(bot: Bot, event: Event) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        info = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id, no_cache=True)
        role = info.get("role", "")
        return role in ("owner", "admin")
    except Exception as e:
        logger.warning(f"Failed to check member role: {e}")
        return False

group_owner_admin_rule = Rule(_is_group_owner_or_admin)
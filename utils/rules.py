import json
import os
from pathlib import Path
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import GroupMessageEvent

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

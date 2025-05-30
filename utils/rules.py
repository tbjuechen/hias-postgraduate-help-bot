import json
import os
from pathlib import Path
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import GroupMessageEvent

import ast

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_allowed_groups():
    try:
        allowed_groups_env = os.getenv("ALLOWED_GROUPS", "[]")
        allowed_groups = set(ast.literal_eval(allowed_groups_env))
        return allowed_groups
    except Exception as e:
        print(f"加载群聊白名单失败: {e}")
        return set()

allowed_groups = load_allowed_groups()

async def only_allowed_group(event: GroupMessageEvent) -> bool:
    return str(event.group_id) in allowed_groups

allow_group_rule = Rule(only_allowed_group)

import json
import os
from pathlib import Path
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import GroupMessageEvent

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_allowed_groups():
    try:
        env_val = os.getenv("ALLOWED_GROUPS", "[]")
        group_list = json.loads(env_val)
        return set(int(group_id) for group_id in group_list)
    except Exception as e:
        print(f"加载群聊白名单失败: {e}")
        return set()

allowed_groups = load_allowed_groups()

async def only_allowed_group(event: GroupMessageEvent) -> bool:
    return event.group_id in allowed_groups

allow_group_rule = Rule(only_allowed_group)

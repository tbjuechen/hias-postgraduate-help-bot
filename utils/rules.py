import yaml
from pathlib import Path
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import GroupMessageEvent

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_allowed_groups():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return set(config.get("allowed_groups", []))
    except Exception as e:
        print(f"加载群聊白名单失败: {e}")
        return set()

allowed_groups = load_allowed_groups()

async def only_allowed_group(event: GroupMessageEvent) -> bool:
    return event.group_id in allowed_groups

allow_group_rule = Rule(only_allowed_group)

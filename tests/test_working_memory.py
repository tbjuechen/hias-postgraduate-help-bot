import os
import sys
from datetime import datetime, timedelta

import pytest

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chat.memory.types.working import WorkingMemory
from chat.memory.base import MemoryItem, MemoryConfig


@pytest.mark.memory
def test_working_memory_add_and_retrieve_basic():
    config = MemoryConfig(working_memory_capacity=5, working_memory_tokens=100)
    wm = WorkingMemory(config)

    item = MemoryItem(
        id="1",
        content="hello world",
        memory_type="working",
        group_id="g1",
        user_id="u1",
        timestamp=datetime.now(),
        metadata={},
    )

    wm.add(item)

    # 不带过滤直接取回
    results = wm.retrieve(query="hello")
    assert len(results) == 1
    assert results[0].id == "1"


@pytest.mark.memory
def test_working_memory_retrieve_with_filters():
    config = MemoryConfig(working_memory_capacity=10, working_memory_tokens=100)
    wm = WorkingMemory(config)

    now = datetime.now()
    items = [
        MemoryItem(id="1", content="a", memory_type="working", group_id="g1", user_id="u1", timestamp=now, metadata={}),
        MemoryItem(id="2", content="b", memory_type="working", group_id="g1", user_id="u2", timestamp=now, metadata={}),
        MemoryItem(id="3", content="c", memory_type="working", group_id="g2", user_id="u1", timestamp=now, metadata={}),
    ]
    for it in items:
        wm.add(it)

    # 按 group_id 过滤
    g1 = wm.retrieve(query="x", group_id="g1")
    assert {m.id for m in g1} == {"1", "2"}

    # 按 user_id 过滤
    u1 = wm.retrieve(query="x", user_id="u1")
    assert {m.id for m in u1} == {"1", "3"}

    # group_id + user_id 同时过滤
    g1_u1 = wm.retrieve(query="x", group_id="g1", user_id="u1")
    assert {m.id for m in g1_u1} == {"1"}


@pytest.mark.memory
def test_working_memory_update_and_remove_and_clear():
    config = MemoryConfig(working_memory_capacity=10, working_memory_tokens=100)
    wm = WorkingMemory(config)

    item = MemoryItem(id="1", content="old text", memory_type="working", group_id="g", user_id="u", timestamp=datetime.now(), metadata={})
    wm.add(item)

    # 更新内容和 metadata
    ok = wm.update("new text here", "1", metadata={"tag": "updated"})
    assert ok is True
    assert wm.memories[0].content == "new text here"
    assert wm.memories[0].metadata["tag"] == "updated"
    assert wm.current_tokens == len("new text here".split())

    # 删除
    assert wm.has_memory("1") is True
    removed = wm.remove("1")
    assert removed is True
    assert wm.has_memory("1") is False
    assert wm.current_tokens == 0

    # 清空
    wm.add(MemoryItem(id="2", content="x y", memory_type="working", group_id="g", user_id="u", timestamp=datetime.now(), metadata={}))
    wm.clear()
    assert wm.get_all() == []
    assert wm.current_tokens == 0


@pytest.mark.memory
def test_working_memory_capacity_and_token_limits():
    config = MemoryConfig(working_memory_capacity=2, working_memory_tokens=3)
    wm = WorkingMemory(config)

    # 每条 2 个 token，总 token 限制 3，会触发删除
    wm.add(MemoryItem(id="1", content="a b", memory_type="working", group_id="g", user_id="u", timestamp=datetime.now(), metadata={}))
    wm.add(MemoryItem(id="2", content="c d", memory_type="working", group_id="g", user_id="u", timestamp=datetime.now(), metadata={}))

    # 由于容量和 token 限制，至少应删除最早的一条
    ids = {m.id for m in wm.get_all()}
    assert "2" in ids
    assert "1" not in ids


@pytest.mark.memory
def test_working_memory_stats_and_recent():
    config = MemoryConfig(working_memory_capacity=10, working_memory_tokens=100)
    wm = WorkingMemory(config)

    base_time = datetime.now() - timedelta(minutes=10)

    item1 = MemoryItem(id="1", content="a", memory_type="working", group_id="g", user_id="u", timestamp=base_time, metadata={})
    item2 = MemoryItem(id="2", content="b", memory_type="working", group_id="g", user_id="u", timestamp=base_time + timedelta(minutes=5), metadata={})

    wm.add(item1)
    wm.add(item2)

    # recent 应按时间倒序
    recent = wm.get_recent(limit=2)
    assert [m.id for m in recent] == ["2", "1"]

    stats = wm.get_stats()
    assert stats["count"] == 2
    assert stats["total_count"] == 2
    assert stats["memory_type"] == "working"

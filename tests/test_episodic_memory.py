import os
import sys
from datetime import datetime, timedelta

import pytest

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chat.memory.types.episodic import EpisodicMemory
from chat.memory.base import MemoryItem, MemoryConfig


@pytest.mark.episodic
def test_episodic_add_retrieve_and_stats(tmp_path, monkeypatch):
    """基础流程：添加几条情景记忆，检索并查看统计信息。"""

    # 使用临时目录避免污染实际数据
    storage_dir = tmp_path / "memory_data"
    storage_dir.mkdir(parents=True, exist_ok=True)

    config = MemoryConfig(
        storage_path=str(storage_dir),
        episodic_memory_retention_days=30,
        episodic_memory_capacity=100,
    )

    # 为了避免真实向量存储带来的依赖，这个测试只关注 SQLite 侧行为
    # 可通过设置不存在的 QDRANT_URL，让 vector_store 初始化失败后在使用中优雅降级
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")  # 无效地址，确保不会连上

    mem = EpisodicMemory(config)

    try:
        now = datetime.now()
        item1 = MemoryItem(
            id="e1",
            content="第一次见到新同学",
            memory_type="episodic",
            user_id="u1",
            group_id="g1",
            timestamp=now - timedelta(days=1),
            metadata={"tag": "meet"},
        )
        item2 = MemoryItem(
            id="e2",
            content="和同学一起讨论作业",
            memory_type="episodic",
            user_id="u1",
            group_id="g1",
            timestamp=now,
            metadata={"tag": "study"},
        )

        mem.add(item1)
        mem.add(item2)

        # 检索应至少能拿到最近的一条
        res = mem.retrieve("作业", top_k=5, user_id="u1", group_id="g1")
        assert any(r.id == "e2" for r in res)

        stats = mem.get_stats()
        assert stats["memory_type"] == "episodic"
        assert stats["total_count"] >= 2
        assert stats["time_span_days"] >= 0.0
    finally:
        if hasattr(mem, "doc_store"):
            mem.doc_store.close()


@pytest.mark.episodic
def test_episodic_forget_by_time_and_capacity(tmp_path, monkeypatch):
    """测试 forget 按时间和容量删除旧的情景记忆。"""

    storage_dir = tmp_path / "memory_data"
    storage_dir.mkdir(parents=True, exist_ok=True)

    config = MemoryConfig(
        storage_path=str(storage_dir),
        episodic_memory_retention_days=7,
        episodic_memory_capacity=2,
    )

    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")

    mem = EpisodicMemory(config)

    try:
        now = datetime.now()
        # 一条很旧的记忆（超过保留天数）
        old_item = MemoryItem(
            id="old",
            content="很久以前的事情",
            memory_type="episodic",
            user_id="u1",
            group_id="g1",
            timestamp=now - timedelta(days=30),
            metadata={},
        )

        # 三条较新的记忆，用于测试容量裁剪
        recent_items = [
            MemoryItem(
                id=f"r{i}",
                content=f"最近的事情 {i}",
                memory_type="episodic",
                user_id="u1",
                group_id="g1",
                timestamp=now - timedelta(days=i),
                metadata={},
            )
            for i in range(3)
        ]

        mem.add(old_item)
        for it in recent_items:
            mem.add(it)

        forgotten = mem.forget()

        # 至少应该删除那条过期的 + 为满足容量再删一些
        assert forgotten >= 2
        # 最终保留数量不超过容量
        remaining_ids = {m.id for m in mem.get_all()}
        assert len(remaining_ids) <= config.episodic_memory_capacity
    finally:
        if hasattr(mem, "doc_store"):
            mem.doc_store.close()

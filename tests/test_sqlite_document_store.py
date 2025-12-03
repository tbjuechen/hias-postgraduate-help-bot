import os
import sys

# 把项目根目录加入 sys.path（假定本文件位于项目根的 tests/ 下）
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
import tempfile
from datetime import datetime

from typing import Generator

import pytest

from chat.memory.storage.document_store import SQLiteDocumentStore


@pytest.fixture()
def temp_db_path() -> Generator[str, None, None]:
    """创建一个临时 SQLite 数据库路径，测试结束后自动删除文件。"""
    fd, path = tempfile.mkstemp(suffix="_memory_store.sqlite3")
    os.close(fd)
    # 先删掉空文件，让 SQLiteDocumentStore 自己创建
    os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def store(temp_db_path: str) -> SQLiteDocumentStore:
    """返回一个基于临时文件的 SQLiteDocumentStore 实例。"""
    return SQLiteDocumentStore(temp_db_path)


@pytest.mark.sqlite
def test_add_and_get_memory(store: SQLiteDocumentStore):
    """测试添加记忆并按 ID 获取。"""
    ts = int(datetime.now().timestamp())
    memory_id = "m_sqlite_1"

    store.add_memory(
        memory_id=memory_id,
        user_id="u1",
        group_id="g1",
        content="hello world",
        memory_type="short_term",
        timestamp=ts,
        properties={"k": "v"},
    )

    got = store.get_memory(memory_id)
    assert got is not None
    assert got["id"] == memory_id
    assert got["user_id"] == "u1"
    assert got["group_id"] == "g1"
    assert got["content"] == "hello world"
    assert got["memory_type"] == "short_term"
    assert got["timestamp"] == ts
    assert isinstance(got.get("properties"), dict)
    assert got["properties"]["k"] == "v"


@pytest.mark.sqlite
def test_search_memories(store: SQLiteDocumentStore):
    """测试按条件搜索记忆。"""
    base_ts = int(datetime.now().timestamp())

    # 插入多条
    for i in range(5):
        store.add_memory(
            memory_id=f"m_sqlite_search_{i}",
            user_id="u_search",
            group_id="g_search",
            content=f"content_{i}",
            memory_type="long_term" if i % 2 == 0 else "short_term",
            timestamp=base_ts + i,
            properties={"idx": i},
        )

    # 只按 user_id / group_id 过滤
    results = store.search_memories(
        user_id="u_search",
        group_id="g_search",
        limit=10,
    )
    assert len(results) == 5

    # 按 memory_type 过滤
    long_term_results = store.search_memories(
        user_id="u_search",
        group_id="g_search",
        memory_type="long_term",
        limit=10,
    )
    assert all(m["memory_type"] == "long_term" for m in long_term_results)

    # 按时间范围过滤
    mid_ts = base_ts + 2
    ranged = store.search_memories(
        user_id="u_search",
        group_id="g_search",
        start_time=mid_ts,
        limit=10,
    )
    assert all(m["timestamp"] >= mid_ts for m in ranged)


@pytest.mark.sqlite
def test_update_memory(store: SQLiteDocumentStore):
    """测试更新记忆内容和属性。"""
    ts = int(datetime.now().timestamp())
    memory_id = "m_sqlite_update"

    store.add_memory(
        memory_id=memory_id,
        user_id="u_upd",
        group_id="g_upd",
        content="old",
        memory_type="short_term",
        timestamp=ts,
        properties={"ver": 1},
    )

    ok = store.update_memory(
        memory_id=memory_id,
        content="new",
        properties={"ver": 2},
    )
    assert ok

    got = store.get_memory(memory_id)
    assert got is not None
    assert got["content"] == "new"
    assert got["properties"]["ver"] == 2


@pytest.mark.sqlite
def test_delete_memory(store: SQLiteDocumentStore):
    """测试删除记忆。"""
    ts = int(datetime.now().timestamp())
    memory_id = "m_sqlite_delete"

    store.add_memory(
        memory_id=memory_id,
        user_id="u_del",
        group_id="g_del",
        content="to be deleted",
        memory_type="short_term",
        timestamp=ts,
        properties=None,
    )

    ok = store.delete_memory(memory_id)
    assert ok
    assert store.get_memory(memory_id) is None


@pytest.mark.sqlite
def test_get_database_stats(store: SQLiteDocumentStore):
    """测试数据库统计信息接口。"""
    stats = store.get_database_stats()
    assert "memory_count" in stats
    assert "group_count" in stats
    assert stats["store_type"] == "SQLite"
    assert os.path.abspath(stats["db_path"]) == os.path.abspath(store.db_path)

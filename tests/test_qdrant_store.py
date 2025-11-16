import os
import sys

# 把项目根目录加入 sys.path（假定本文件位于项目根的 tests/ 下）
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
import time
from datetime import datetime

import pytest

from chat.memory.storage.qdrant_store import QdrantConnectionManager, QdrantVectorStore


@pytest.fixture(scope="module")
def qdrant_store() -> "QdrantVectorStore":
    """提供一个用于测试的 QdrantVectorStore 实例。

    依赖本地运行的 Qdrant（默认 http://localhost:6333）。
    如果本地没有 Qdrant，将在健康检查时直接跳过测试。
    """
    store = QdrantConnectionManager.get_instance(
        url=None,                # None = 本地 localhost:6333
        api_key=None,            # 无鉴权
        collection_name="test_memory_store_pytest",
        vector_size=4,
        distance="cosine",
        timeout=10,
    )
    return store


@pytest.mark.qdrant
def test_health_check(qdrant_store: QdrantVectorStore):
    """基本健康检查：确认 Qdrant 可用，否则跳过后续测试。"""
    if not qdrant_store.health_check():
        pytest.skip("Qdrant 健康检查失败，可能本地服务未启动")


@pytest.mark.qdrant
def test_add_and_search_vectors(qdrant_store: QdrantVectorStore):
    """测试向 Qdrant 添加向量并进行搜索。"""
    if not qdrant_store.health_check():
        pytest.skip("Qdrant 不可用，跳过测试")

    vectors = [
        [0.1, 0.2, 0.3, 0.4],
        [0.2, 0.1, 0.0, 0.9],
        [0.9, 0.1, 0.3, 0.1],
    ]
    now_ts = int(datetime.now().timestamp())
    metadata = [
        {
            "memory_id": f"m_pytest_{i}",
            "memory_type": "pytest",
            "user_id": "u_pytest",
            "group_id": "g_pytest",
            "importance": i,
            "is_rag_data": False,
            "rag_namespace": "test_ns",
            "data_source": "pytest",
            "created_at": now_ts,
        }
        for i in range(len(vectors))
    ]

    ok = qdrant_store.add_vector(vectors=vectors, metadata=metadata)
    assert ok, "add_vector 应该返回 True"

    # 稍等，确保 upsert 完成
    time.sleep(1)

    query = [0.1, 0.2, 0.3, 0.4]
    where = {"group_id": "g_pytest", "memory_type": "pytest"}
    results = qdrant_store.search_vectors(query=query, top_k=3, where=where)

    assert isinstance(results, list)
    assert len(results) > 0, "搜索结果不应为空"
    for r in results:
        assert "id" in r
        assert "score" in r
        assert "metadata" in r
        assert r["metadata"].get("group_id") == "g_pytest"


@pytest.mark.qdrant
def test_delete_memories(qdrant_store: QdrantVectorStore):
    """测试基于 payload.memory_id 的删除逻辑。"""
    if not qdrant_store.health_check():
        pytest.skip("Qdrant 不可用，跳过测试")

    # 先再插入两条，避免前一个测试删除干净
    vectors = [
        [0.5, 0.5, 0.5, 0.5],
        [0.6, 0.6, 0.6, 0.6],
    ]
    now_ts = int(datetime.now().timestamp())
    memory_ids = [f"m_pytest_del_{i}" for i in range(len(vectors))]
    metadata = [
        {
            "memory_id": mid,
            "memory_type": "pytest",
            "user_id": "u_pytest",
            "group_id": "g_pytest",
            "importance": 1,
            "is_rag_data": False,
            "rag_namespace": "test_ns",
            "data_source": "pytest",
            "created_at": now_ts,
        }
        for mid in memory_ids
    ]

    ok = qdrant_store.add_vector(vectors=vectors, metadata=metadata)
    assert ok, "add_vector 应该返回 True (for delete test)"
    time.sleep(1)

    # 删除这两条
    qdrant_store.delete_memories(memory_ids)

    # 再查一次，确认这两条 memory_id 不再出现
    query = [0.5, 0.5, 0.5, 0.5]
    where = {"group_id": "g_pytest", "memory_type": "pytest"}
    results = qdrant_store.search_vectors(query=query, top_k=10, where=where)

    remaining_ids = {r["metadata"].get("memory_id") for r in results}
    for mid in memory_ids:
        assert mid not in remaining_ids, f"memory_id={mid} 应该已被删除"

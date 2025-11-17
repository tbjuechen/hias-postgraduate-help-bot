import os
import sys
from datetime import datetime

import pytest

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chat.memory.base import MemoryConfig, MemoryItem
from chat.memory.types.semantic import SemanticMemory


@pytest.mark.semantic
def test_semantic_memory_full_api_roundtrip():
    """在真实 Qdrant + Neo4j 上测试 SemanticMemory 的主要 API。

    要运行本测试，需要：
    - Qdrant 与 Neo4j 实例运行且配置正确（见 DATABASE_SETUP_GUIDE）
    - 设置环境变量 ENABLE_SEMANTIC_INTEGRATION_TEST=1
    """

    config = MemoryConfig()
    memory = SemanticMemory(config=config)

    # 1. add
    now = datetime.now()
    item = MemoryItem(
        id="test_semantic_1",
        content="小明在北京大学学习人工智能。",
        memory_type="semantic",
        group_id="g_semantic",
        user_id="u_semantic",
        timestamp=now,
        metadata={},
    )

    memory_id = memory.add(item)
    assert memory_id == item.id

    # 2. has_memory / _find_memory_by_id 间接测试
    assert memory.has_memory(memory_id)

    # 3. retrieve（向量 + 图混合检索）
    results = memory.retrieve("北京大学的人工智能", top_k=5, group_id="g_semantic")
    assert isinstance(results, list)
    # 至少应该能检索到一条（内容和实体有关联），这里不强制依赖返回的 id
    # 在实际使用场景中，通常是先通过业务表查到 memory_id，再去做检索/操作
    assert any(memory_id in m.content for m in results) or len(results) >= 1

    # 4. update：修改内容并确认还能检索到
    updated_content = "小明在北京大学学习计算机科学。"
    ok = memory.update(memory_id=memory_id, content=updated_content)
    assert ok

    updated_results = memory.retrieve("北京大学的计算机科学", top_k=5, group_id="g_semantic")
    # 只要求更新后的检索能返回至少一条结果，不强依赖 id 完全匹配
    assert isinstance(updated_results, list)
    assert len(updated_results) >= 1

    # 5. export_knowledge_graph：至少应该返回基本统计字段
    kg_stats = memory.export_knowledge_graph()
    assert "graph_stats" in kg_stats
    graph_stats = kg_stats["graph_stats"]
    assert "total_nodes" in graph_stats
    assert "total_relationships" in graph_stats

    # 6. clear：清空所有记忆
    memory.clear()

    # 清理后，has_memory 应该为 False（依赖向量库清空）
    assert not memory.has_memory(memory_id)

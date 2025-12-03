import os
import sys
import uuid

import pytest

from dotenv import load_dotenv

load_dotenv()

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from chat.memory.storage.neo4j_store import Neo4jGraphStore


@pytest.mark.neo4j
@pytest.mark.integration
def test_neo4j_graph_store_basic_crud():
    """使用真实 Neo4j 实例测试 Neo4jGraphStore 的核心功能。

    需要环境变量提供连接信息：
    - NEO4J_URI (默认: bolt://localhost:7687)
    - NEO4J_USER (默认: neo4j)
    - NEO4J_PASSWORD (无默认，未设置则跳过测试)
    - NEO4J_DATABASE (默认: neo4j)
    """
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        pytest.skip("NEO4J_PASSWORD 未设置，跳过 Neo4j 集成测试")

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    store = Neo4jGraphStore(
        uri=uri,
        username=user,
        password=password,
        database=database,
    )

    assert store.health_check() is True

    # 确保测试环境干净（仅影响测试用数据）
    store.clear_all()

    # 创建两个实体
    e1_id = f"test_entity_{uuid.uuid4()}"
    e2_id = f"test_entity_{uuid.uuid4()}"

    assert store.add_entity(e1_id, "测试实体1", "Person") is True
    assert store.add_entity(e2_id, "测试实体2", "Course") is True

    # 创建关系
    rel_type = "RELATED_TO"
    assert store.add_relationship(e1_id, e2_id, rel_type) is True

    # 查询相关实体
    related = store.find_related_entities(e1_id, relationship_types=[rel_type], max_depth=1)
    target_ids = {item["id"] for item in related}
    assert e2_id in target_ids

    # 查询关系详情
    rels = store.get_entity_relationships(e1_id)
    assert any(r["other_entity"].get("id") == e2_id for r in rels)

    # 统计信息
    stats = store.get_stats()
    assert stats.get("total_nodes", 0) >= 2
    assert stats.get("total_relationships", 0) >= 1

    # 删除实体
    assert store.delete_entity(e1_id) is True
    assert store.delete_entity(e2_id) is True

    # 再次统计，节点应减少
    stats_after = store.get_stats()
    assert stats_after.get("entity_nodes", 0) <= stats.get("entity_nodes", 0)

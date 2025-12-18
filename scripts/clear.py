import os
import sys
from pathlib import Path

# 尝试加载 .env 文件，以便获取数据库连接配置
try:
    from dotenv import load_dotenv
    # 加载项目根目录下的 .env
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量: {env_path}")
except ImportError:
    print("⚠️ 未检测到 python-dotenv，将使用当前系统环境变量 (pip install python-dotenv)")

def clear_sqlite():
    """1. 物理删除 SQLite 数据库文件"""
    print("\n[1/3] 清理 SQLite (情景记忆)...")
    
    # 获取配置的存储路径，默认为 ./data/memory_storage
    default_dir = "./data/memory_storage"
    storage_path = os.getenv("STORAGE_PATH", default_dir)
    
    # 处理相对路径，使其相对于项目根目录
    if not os.path.isabs(storage_path):
        project_root = Path(__file__).resolve().parent.parent
        storage_path = project_root / storage_path
    
    db_file = Path(storage_path) / "memory.db"
    
    if db_file.exists():
        try:
            os.remove(db_file)
            print(f"✅ 已删除数据库文件: {db_file}")
        except Exception as e:
            print(f"❌ 删除 SQLite 文件失败: {e}")
            print("   (请确保没有任何程序正在占用该文件)")
    else:
        print(f"ℹ️ SQLite 文件不存在，无需清理: {db_file}")

def clear_neo4j():
    """2. 连接 Neo4j 并清空所有图数据"""
    print("\n[2/3] 清理 Neo4j (语义记忆 - 图谱)...")
    
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        # 验证连接
        driver.verify_connectivity()
        
        with driver.session() as session:
            # 运行 Cypher 语句清空数据库
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            nodes_deleted = summary.counters.nodes_deleted
            rels_deleted = summary.counters.relationships_deleted
            print(f"✅ Neo4j 清空完成: 删除了 {nodes_deleted} 个节点, {rels_deleted} 条关系")
            
        driver.close()
    except ImportError:
        print("❌ 未安装 neo4j 驱动，跳过 (pip install neo4j)")
    except Exception as e:
        print(f"❌ Neo4j 连接或清理失败: {e}")
        print("   (请检查 NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD 配置)")

def clear_qdrant():
    """3. 连接 Qdrant 并删除向量集合"""
    print("\n[3/3] 清理 Qdrant (语义/情景向量)...")
    
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", None)
    
    # 需要清理的 Collection 名称列表
    # 根据您的配置，这里列出了可能的集合名称
    target_collections = [
        os.getenv("QDRANT_COLLECTION", "memory_vectors"), # 情景记忆默认
        "semantic_memory", # 语义记忆常见名
        "memory_storage"
    ]
    
    try:
        from qdrant_client import QdrantClient
        
        client = QdrantClient(url=url, api_key=api_key)
        
        # 获取当前存在的集合列表
        try:
            response = client.get_collections()
            existing_collections = [c.name for c in response.collections]
        except Exception:
            # 如果获取列表失败，尝试直接删除目标
            existing_collections = target_collections

        deleted_count = 0
        for collection_name in set(target_collections):
            if collection_name in existing_collections:
                try:
                    client.delete_collection(collection_name)
                    print(f"✅ 已删除 Collection: {collection_name}")
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ 删除 Collection {collection_name} 失败: {e}")
        
        if deleted_count == 0:
            print("ℹ️ 未发现目标 Collection，无需清理")
            
    except ImportError:
        print("❌ 未安装 qdrant-client，跳过 (pip install qdrant-client)")
    except Exception as e:
        print(f"❌ Qdrant 连接或清理失败: {e}")
        print("   (请检查 QDRANT_URL 配置)")

if __name__ == "__main__":
    print("="*50)
    print("🧨  环境重置工具 (Scripts/clear_all.py)")
    print("⚠️   警告：这将永久删除所有记忆数据！")
    print("     - 删除 memory.db 文件")
    print("     - 清空 Neo4j 图数据库")
    print("     - 删除 Qdrant 向量集合")
    print("="*50)
    
    confirm = input("❓ 确认执行全部清理吗？(输入 yes 确认): ")
    
    if confirm.strip().lower() == "yes":
        try:
            clear_sqlite()
            clear_neo4j()
            clear_qdrant()
            print("\n✨ 环境已成功重置！")
        except KeyboardInterrupt:
            print("\n🚫 操作已中断")
    else:
        print("已取消。")
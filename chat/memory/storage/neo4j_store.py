from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from loguru import logger

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None

class Neo4jGraphStore:
    """Neo4j图数据库存储类"""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "12345678",
        database: str = "neo4j",
        max_connection_lifetime: int = 3600,
        max_connection_pool_size: int = 50,
        connection_acquisition_timeout: int = 60,
        **kwargs
    ):
        """
        初始化Neo4j图数据库存储类

        :param uri: Neo4j连接URI
        :param username: 用户名
        :param password: 密码
        :param database: 数据库名称
        :param max_connection_lifetime: 最大连接生命周期(秒)
        :param max_connection_pool_size: 最大连接池大小
        :param connection_acquisition_timeout: 连接获取超时(秒)
        """
        if not NEO4J_AVAILABLE:
            raise ImportError(
                "neo4j未安装。请运行: pip install neo4j>=5.0.0"
            )
        
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        
        # 初始化驱动
        self.driver = None
        self._initialize_driver(
            max_connection_lifetime=max_connection_lifetime,
            max_connection_pool_size=max_connection_pool_size,
            connection_acquisition_timeout=connection_acquisition_timeout
        )
        
        # 创建索引
        self._create_indexes()

    def _initialize_driver(self, **config):
        """初始化Neo4j驱动"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                **config
            )
            
            # 验证连接
            self.driver.verify_connectivity()
            
            # 检查是否是云服务
            if "neo4j.io" in self.uri or "aura" in self.uri.lower():
                logger.info(f"✅ 成功连接到Neo4j云服务: {self.uri}")
            else:
                logger.info(f"✅ 成功连接到Neo4j服务: {self.uri}")
                
        except AuthError as e:
            logger.error(f"❌ Neo4j认证失败: {e}")
            logger.info("💡 请检查用户名和密码是否正确")
            raise
        except ServiceUnavailable as e:
            logger.error(f"❌ Neo4j服务不可用: {e}")
            if "localhost" in self.uri:
                logger.info("💡 本地连接失败，可以考虑使用Neo4j Aura云服务")
                logger.info("💡 或启动本地服务: docker run -p 7474:7474 -p 7687:7687 neo4j:5.14")
            else:
                logger.info("💡 请检查URL和网络连接")
            raise
        except Exception as e:
            logger.error(f"❌ Neo4j连接失败: {e}")
            raise

    def _create_indexes(self):
        """创建必要的索引以提高查询性能"""
        indexes = [
            # 实体索引
            "CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) ON (e.id)",
            "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX entity_type_index IF NOT EXISTS FOR (e:Entity) ON (e.type)",
            
            # 记忆索引
            "CREATE INDEX memory_id_index IF NOT EXISTS FOR (m:Memory) ON (m.id)",
            "CREATE INDEX memory_type_index IF NOT EXISTS FOR (m:Memory) ON (m.memory_type)",
            "CREATE INDEX memory_timestamp_index IF NOT EXISTS FOR (m:Memory) ON (m.timestamp)",
        ]
        
        with self.driver.session(database=self.database) as session:
            for index_query in indexes:
                try:
                    session.run(index_query)
                except Exception as e:
                    logger.debug(f"索引创建跳过 (可能已存在): {e}")
        
        logger.info("✅ Neo4j索引创建完成")

    def add_entity(self, entity_id: str, name: str, entity_type: str, properties: Dict[str, Any] = None) -> bool:
        """
        添加实体节点

        :param entity_id: 实体唯一ID
        :param name: 实体名称
        :param entity_type: 实体类型
        :param properties: 其他属性字典
        :return: 是否添加成功
        """
        try:
            props = properties or {}
            props.update({
                "id": entity_id,
                "name": name,
                "type": entity_type,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
            
            query = """
            MERGE (e:Entity {id: $entity_id})
            SET e += $properties
            RETURN e
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, entity_id=entity_id, properties=props)
                record = result.single()
                
                if record:
                    logger.debug(f"✅ 添加实体: {name} ({entity_type})")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"❌ 添加实体失败: {e}")
            return False
        
    def add_relationship(
        self, 
        from_entity_id: str, 
        to_entity_id: str, 
        relationship_type: str,
        properties: Dict[str, Any] = None
    ) -> bool:
        """
        添加实体关系

        :param from_entity_id: 起始实体ID
        :param to_entity_id: 目标实体ID
        :param relationship_type: 关系类型
        :param properties: 其他属性字典
        :return: 是否添加成功
        """
        try:
            props = properties or {}
            props.update({
                "type": relationship_type,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
            
            query = f"""
            MATCH (from:Entity {{id: $from_id}})
            MATCH (to:Entity {{id: $to_id}})
            MERGE (from)-[r:{relationship_type}]->(to)
            SET r += $properties
            RETURN r
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    query,
                    from_id=from_entity_id,
                    to_id=to_entity_id,
                    properties=props
                )
                record = result.single()
                
                if record:
                    logger.debug(f"✅ 添加关系: {from_entity_id} -{relationship_type}-> {to_entity_id}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"❌ 添加关系失败: {e}")
            return False
        
    def find_related_entities(
        self, 
        entity_id: str, 
        relationship_types: List[str] = None,
        max_depth: int = 2,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        查找相关实体

        :param entity_id: 实体ID
        :param relationship_types: 关系类型列表
        :param max_depth: 最大搜索深度
        :param limit: 返回结果数量限制
        :return: 相关实体列表
        """
        try:
            # 构建关系类型过滤
            rel_filter = ""
            if relationship_types:
                rel_types = "|".join(relationship_types)
                rel_filter = f":{rel_types}"
            
            query = f"""
            MATCH path = (start:Entity {{id: $entity_id}})-[r{rel_filter}*1..{max_depth}]-(related:Entity)
            WHERE start.id <> related.id
            RETURN DISTINCT related, 
                   length(path) as distance,
                   [rel in relationships(path) | type(rel)] as relationship_path
            ORDER BY distance, related.name
            LIMIT $limit
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, entity_id=entity_id, limit=limit)
                
                entities = []
                for record in result:
                    entity_data = dict(record["related"])
                    entity_data["distance"] = record["distance"]
                    entity_data["relationship_path"] = record["relationship_path"]
                    entities.append(entity_data)
                
                logger.debug(f"🔍 找到 {len(entities)} 个相关实体")
                return entities
                
        except Exception as e:
            logger.error(f"❌ 查找相关实体失败: {e}")
            return []
        
    def search_entities_by_name(self, name_pattern: str, entity_types: List[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        按名称模式搜索实体

        :param name_pattern: 名称模式（支持通配符）
        :param entity_types: 实体类型列表
        :param limit: 返回结果数量限制
        :return: 实体列表
        """
        try:
            # 构建类型过滤
            type_filter = ""
            params = {"pattern": f".*{name_pattern}.*", "limit": limit}
            
            if entity_types:
                type_filter = "AND e.type IN $types"
                params["types"] = entity_types
            
            query = f"""
            MATCH (e:Entity)
            WHERE e.name =~ $pattern {type_filter}
            RETURN e
            ORDER BY e.name
            LIMIT $limit
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, **params)
                
                entities = []
                for record in result:
                    entity_data = dict(record["e"])
                    entities.append(entity_data)
                
                logger.debug(f"🔍 按名称搜索到 {len(entities)} 个实体")
                return entities
                
        except Exception as e:
            logger.error(f"❌ 按名称搜索实体失败: {e}")
            return []
    
    def get_entity_relationships(self, entity_id: str) -> List[Dict[str, Any]]:
        """
        获取实体的所有关系
        
        :param entity_id: 实体ID
        :return: 关系列表
        """
        try:
            query = """
            MATCH (e:Entity {id: $entity_id})-[r]-(other:Entity)
            RETURN r, other, 
                   CASE WHEN startNode(r).id = $entity_id THEN 'outgoing' ELSE 'incoming' END as direction
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, entity_id=entity_id)
                
                relationships = []
                for record in result:
                    rel_data = dict(record["r"])
                    other_data = dict(record["other"])
                    
                    relationship = {
                        "relationship": rel_data,
                        "other_entity": other_data,
                        "direction": record["direction"]
                    }
                    relationships.append(relationship)
                
                return relationships
                
        except Exception as e:
            logger.error(f"❌ 获取实体关系失败: {e}")
            return []
        
    

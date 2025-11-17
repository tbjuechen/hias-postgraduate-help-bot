from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
import json
import math
import numpy as np

from loguru import logger

from ..base import BaseMemory, MemoryItem, MemoryConfig
from ..embedding import get_dimension, get_text_embedder
from ...core.database_config import get_database_config

class Entity:
    """实体类"""
    
    def __init__(
        self,
        entity_id: str,
        name: str,
        entity_type: str = "MISC",
        description: str = "",
        properties: Dict[str, Any] = None
    ):
        self.entity_id = entity_id
        self.name = name
        self.entity_type = entity_type  # PERSON, ORG, PRODUCT, SKILL, CONCEPT等
        self.description = description
        self.properties = properties or {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.frequency = 1  # 出现频率
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "properties": self.properties,
            "frequency": self.frequency
        }
    
class Relation:
    """关系类"""
    
    def __init__(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        strength: float = 1.0,
        evidence: str = "",
        properties: Dict[str, Any] = None
    ):
        self.from_entity = from_entity
        self.to_entity = to_entity
        self.relation_type = relation_type
        self.strength = strength
        self.evidence = evidence  # 支持该关系的原文本
        self.properties = properties or {}
        self.created_at = datetime.now()
        self.frequency = 1  # 关系出现频率
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "evidence": self.evidence,
            "properties": self.properties,
            "frequency": self.frequency
        }

class SemanticMemory(BaseMemory):
    """语义记忆实现"""

    def __init__(self, config: MemoryConfig, storage_backend=None):
        super().__init__(config, storage_backend)
        
        # 嵌入模型（统一提供）
        self.embedding_model = None
        self._init_embedding_model()

        # 专业数据库存储
        self.vector_store = None
        self.graph_store = None
        self._init_databases()

        self.nlp = None
        self._init_nlp()

        logger.info("增强语义记忆初始化完成（使用Qdrant+Neo4j专业数据库）")

    
    def _init_embedding_model(self):
        """初始化统一嵌入模型（由 embedding_provider 管理）。"""
        try:
            self.embedding_model = get_text_embedder()
            # 轻量健康检查与日志
            try:
                test_vec = self.embedding_model.encode("health_check")
                dim = getattr(self.embedding_model, "dimension", len(test_vec))
                logger.info(f"✅ 嵌入模型就绪，维度: {dim}")
            except Exception:
                logger.info("✅ 嵌入模型就绪")
        except Exception as e:
            logger.error(f"❌ 嵌入模型初始化失败: {e}")
            raise

    def _init_databases(self):
        """初始化专业数据库存储"""
        try:
            # 获取数据库配置
            db_config = get_database_config()
            
            # 初始化Qdrant向量数据库（使用连接管理器避免重复连接）
            from ..storage.qdrant_store import QdrantConnectionManager
            qdrant_config = db_config.get_qdrant_config() or {}
            qdrant_config["vector_size"] = get_dimension()
            self.vector_store = QdrantConnectionManager.get_instance(**qdrant_config)
            logger.info("✅ Qdrant向量数据库初始化完成")
            
            # 初始化Neo4j图数据库
            from ..storage.neo4j_store import Neo4jGraphStore
            neo4j_config = db_config.get_neo4j_config()
            self.graph_store = Neo4jGraphStore(**neo4j_config)
            logger.info("✅ Neo4j图数据库初始化完成")
            
            # 验证连接
            vector_health = self.vector_store.health_check()
            graph_health = self.graph_store.health_check()
            
            if not vector_health:
                logger.warning("⚠️ Qdrant连接异常，部分功能可能受限")
            if not graph_health:
                logger.warning("⚠️ Neo4j连接异常，图搜索功能可能受限")
            
            logger.info(f"🏥 数据库健康状态: Qdrant={'✅' if vector_health else '❌'}, Neo4j={'✅' if graph_health else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            logger.info("💡 请检查数据库配置和网络连接")
            logger.info("💡 参考 DATABASE_SETUP_GUIDE.md 进行配置")
            raise

    def _init_nlp(self):
        """初始化NLP处理器 - 智能多语言支持"""
        try:
            import spacy
            self.nlp_models = {}
            
            # 尝试加载多语言模型
            models_to_try = [
                ("zh_core_web_sm", "中文"),
                ("en_core_web_sm", "英文")
            ]
            
            loaded_models = []
            for model_name, lang_name in models_to_try:
                try:
                    nlp = spacy.load(model_name)
                    self.nlp_models[model_name] = nlp
                    loaded_models.append(lang_name)
                    logger.info(f"✅ 加载{lang_name}spaCy模型: {model_name}")
                except OSError:
                    logger.warning(f"⚠️ {lang_name}spaCy模型不可用: {model_name}")
            
            # 设置主要NLP处理器
            if "zh_core_web_sm" in self.nlp_models:
                self.nlp = self.nlp_models["zh_core_web_sm"]
                logger.info("🎯 主要使用中文spaCy模型")
            elif "en_core_web_sm" in self.nlp_models:
                self.nlp = self.nlp_models["en_core_web_sm"]
                logger.info("🎯 主要使用英文spaCy模型")
            else:
                self.nlp = None
                logger.warning("⚠️ 无可用spaCy模型，实体提取将受限")
            
            if loaded_models:
                logger.info(f"📚 可用语言模型: {', '.join(loaded_models)}")
                
        except ImportError:
            logger.warning("⚠️ spaCy不可用，实体提取将受限")
            self.nlp = None
            self.nlp_models = {}

    def add(self, memory_item: MemoryItem) -> str:
        """添加语义记忆"""
        try:
            # 1. 计算嵌入向量
            embedding = self.embedding_model.encode(memory_item.content)
            # 兼容 ndarray / list 等多种返回类型
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()

            # 2. 提取实体和关系
            entities = self._extract_entities(memory_item.content)
            relations = self._extract_relations(memory_item.content, entities)

            # 3. 存储到Neo4j图数据库
            for entity in entities:
                self._add_entity_to_graph(entity, memory_item)
            
            for relation in relations:
                self._add_relation_to_graph(relation, memory_item)
            
            # 4. 存储到Qdrant向量数据库
            metadata = {
                "memory_id": memory_item.id,
                "user_id": self.memory_type,
                "group_id": memory_item.group_id,
                "content": memory_item.content,
                "memory_type": memory_item.memory_type,
                "timestamp": int(memory_item.timestamp.timestamp()),
                "entities": [e.entity_id for e in entities],
                "entity_count": len(entities),
                "relation_count": len(relations)
            }

            success = self.vector_store.add_vector(
                vectors=[embedding],
                metadata=[metadata],
                ids=[memory_item.id]
            )

            if not success:
                logger.warning("⚠️ 向量存储失败，但记忆已添加到图数据库")
            
            logger.info(f"✅ 添加语义记忆: {len(entities)}个实体, {len(relations)}个关系")
            return memory_item.id
        
        except Exception as e:
            logger.error(f"❌ 添加语义记忆失败: {e}")
            raise

    def _vector_search(self, query: str, top_k: int = 5, group_id: str = None) -> List[Dict[str, Any]]:
        """在向量数据库中搜索相关记忆"""
        try:
            # 生成查询向量
            query_embedding = self.embedding_model.encode(query)
            if hasattr(query_embedding, "tolist"):
                query_embedding = query_embedding.tolist()
            
            # 构建过滤条件
            where_filter = {"memory_type": "semantic"}
            if group_id:
                where_filter["group_id"] = group_id

            # Qdrant向量检索
            results = self.vector_store.search_vectors(
                query=query_embedding,
                top_k=top_k,
                where=where_filter if where_filter else None
            )

            # 转换结果格式：使用 payload.memory_id 作为逻辑ID，metadata 单独存放
            formatted_results = []
            for result in results:
                meta = result.get("metadata", {}) or {}
                logical_id = meta.get("memory_id", result.get("id"))

                formatted_result = {
                    "id": logical_id,
                    "score": float(result.get("score", 0.0)),
                    "metadata": meta,
                    "content": meta.get("content", ""),
                    "user_id": meta.get("user_id"),
                    "group_id": meta.get("group_id"),
                    "memory_type": meta.get("memory_type"),
                    "timestamp": meta.get("timestamp"),
                    "entities": meta.get("entities", []),
                }
                formatted_results.append(formatted_result)

            logger.debug(f"🔍 Qdrant向量搜索返回 {len(formatted_results)} 个结果")
            return formatted_results
    
        except Exception as e:
            logger.error(f"❌ 向量搜索失败: {e}")
            return []

    def _graph_search(self, query: str, limit: int, group_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Neo4j图搜索（简化版：按实体名称查相关 memory_id）。

        当前实现不依赖 Entity.id 的 hash 一致性，而是：
        1. 从查询中抽取实体（如 "北京大学"）。
        2. 用名称模糊搜索图中的实体节点。
        3. 直接从这些实体节点的属性中读取 memory_id。
        """
        try:
            # 从查询中提取实体
            query_entities = self._extract_entities(query)

            if not query_entities:
                # 如果没有提取到实体，尝试按名称搜索
                entities_by_name = self.graph_store.search_entities_by_name(
                    name_pattern=query,
                    limit=10
                )
                if entities_by_name:
                    query_entities = [Entity(
                        entity_id=e["id"],
                        name=e["name"],
                        entity_type=e["type"]
                    ) for e in entities_by_name[:3]]
                else:
                    return []
            
            # 直接通过实体名称，从实体节点属性中读取 memory_id
            related_memory_ids: set[str] = set()

            for entity in query_entities:
                try:
                    entities_by_name = self.graph_store.search_entities_by_name(
                        name_pattern=entity.name,
                        limit=20,
                    )
                    for e in entities_by_name:
                        mem_id = e.get("memory_id")
                        if mem_id:
                            related_memory_ids.add(mem_id)
                except Exception as e:
                    logger.debug(f"图搜索实体 {entity.name} 失败: {e}")
                    continue
            
            # 构建结果 - 从向量数据库获取完整记忆信息_find_memory_by_id
            results = []
            for memory_id in list(related_memory_ids)[:limit * 2]:  # 获取更多候选
                try:
                    # 优先从本地缓存获取记忆详情，避免占位向量维度不一致问题
                    mem = self._find_memory_by_id(memory_id)
                    if not mem:
                        continue

                    if group_id and mem.group_id != group_id:
                        continue

                    metadata = {
                        "content": mem.content,
                        "user_id": mem.user_id,
                        "group_id": mem.group_id,
                        "memory_type": mem.memory_type,
                        "timestamp": int(mem.timestamp.timestamp()),
                        "entities": mem.metadata.get("entities", []),
                        "entity_count": mem.metadata.get("entity_count", 0),
                        "relation_count": mem.metadata.get("relation_count", 0),
                    }

                    # 计算图相关性分数
                    graph_score = self._calculate_graph_relevance_neo4j(metadata, query_entities)

                    results.append({
                        "id": memory_id,
                        "memory_id": memory_id,
                        "content": metadata.get("content", ""),
                        "similarity": graph_score,
                        "user_id": metadata.get("user_id"),
                        'group_id': metadata.get("group_id"),
                        "memory_type": metadata.get("memory_type"),
                        "timestamp": metadata.get("timestamp"),
                        "entities": metadata.get("entities", [])
                    })

                except Exception as e:
                    logger.debug(f"获取记忆 {memory_id} 详情失败: {e}")
                    continue
            
            # 按图相关性排序
            results.sort(key=lambda x: x["similarity"], reverse=True)
            logger.debug(f"🕸️ Neo4j图搜索返回 {len(results)} 个结果")
            return results[:limit]

        except Exception as e:
            logger.error(f"❌ Neo4j图搜索失败: {e}")
            return []
        
    def _find_memory_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """根据记忆ID查找记忆项"""
        try:
            # 通过 payload 过滤 memory_id 获取点数据
            raw_results = self.vector_store.search_vectors(
                query=[0.0] * self.vector_store.vector_size,
                top_k=1,
                where={"memory_id": memory_id},
            )

            if not raw_results:
                return None

            data = raw_results[0].get("metadata", {})
            if not data:
                return None

            mem_item = MemoryItem(
                id=data.get("memory_id", ""),
                content=data.get("content", ""),
                memory_type=data.get("memory_type", ""),
                group_id=data.get("group_id", ""),
                user_id=data.get("user_id", ""),
                timestamp=datetime.fromtimestamp(data.get("timestamp", 0)),
                metadata=data,
            )
            return mem_item
        except Exception as e:
            logger.error(f"❌ 查找记忆 {memory_id} 失败: {e}")
            return None
        
    def _detect_language(self, text: str) -> str:
        """简单的语言检测"""
        # 统计中文字符比例（无正则，逐字符判断范围）
        chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
        total_chars = len(text.replace(' ', ''))
        
        if total_chars == 0:
            return "en"
        
        chinese_ratio = chinese_chars / total_chars
        return "zh" if chinese_ratio > 0.3 else "en"
    
    def _extract_entities(self, text: str) -> List[Entity]:
        """智能多语言实体提取"""
        entities = []
        
        # 检测文本语言
        lang = self._detect_language(text)
        
        # 选择合适的spaCy模型
        selected_nlp = None
        if lang == "zh" and "zh_core_web_sm" in self.nlp_models:
            selected_nlp = self.nlp_models["zh_core_web_sm"]
        elif lang == "en" and "en_core_web_sm" in self.nlp_models:
            selected_nlp = self.nlp_models["en_core_web_sm"]
        else:
            # 使用默认模型
            selected_nlp = self.nlp
        
        logger.debug(f"🌐 检测语言: {lang}, 使用模型: {selected_nlp.meta['name'] if selected_nlp else 'None'}")
        
        # 使用spaCy进行实体识别和词法分析
        if selected_nlp:
            try:
                doc = selected_nlp(text)
                logger.debug(f"📝 spaCy处理文本: '{text}' -> {len(doc.ents)} 个实体")
                
                # 存储词法分析结果，供Neo4j使用
                self._store_linguistic_analysis(doc, text)
                
                if not doc.ents:
                    # 如果没有实体，记录详细的词元信息
                    logger.debug("🔍 未找到实体，词元分析:")
                    for token in doc[:5]:  # 只显示前5个词元
                        logger.debug(f"   '{token.text}' -> POS: {token.pos_}, TAG: {token.tag_}, ENT_IOB: {token.ent_iob_}")
                
                for ent in doc.ents:
                    entity = Entity(
                        entity_id=f"entity_{hash(ent.text)}",
                        name=ent.text,
                        entity_type=ent.label_,
                        description=f"从文本中识别的{ent.label_}实体"
                    )
                    entities.append(entity)
                    # 安全获取置信度信息
                    confidence = "N/A"
                    try:
                        if hasattr(ent._, 'confidence'):
                            confidence = getattr(ent._, 'confidence', 'N/A')
                    except:
                        confidence = "N/A"
                    
                    logger.debug(f"🏷️ spaCy识别实体: '{ent.text}' -> {ent.label_} (置信度: {confidence})")
                
            except Exception as e:
                logger.warning(f"⚠️ spaCy实体识别失败: {e}")
                import traceback
                logger.debug(f"详细错误: {traceback.format_exc()}")
        else:
            logger.warning("⚠️ 没有可用的spaCy模型进行实体识别")
        
        return entities
    
    def _store_linguistic_analysis(self, doc, text: str):
        """存储spaCy词法分析结果到Neo4j"""
        if not self.graph_store:
            return
            
        try:
            # 为每个词元创建节点
            for token in doc:
                # 跳过标点符号和空格
                if token.is_punct or token.is_space:
                    continue
                    
                token_id = f"token_{hash(token.text + token.pos_)}"
                
                # 添加词元节点到Neo4j
                self.graph_store.add_entity(
                    entity_id=token_id,
                    name=token.text,
                    entity_type="TOKEN",
                    properties={
                        "pos": token.pos_,        # 词性（NOUN, VERB等）
                        "tag": token.tag_,        # 细粒度标签
                        "lemma": token.lemma_,    # 词元原形
                        "is_alpha": token.is_alpha,
                        "is_stop": token.is_stop,
                        "source_text": text[:50],  # 来源文本片段
                        "language": self._detect_language(text)
                    }
                )
                
                # 如果是名词，可能是潜在的概念
                if token.pos_ in ["NOUN", "PROPN"]:
                    concept_id = f"concept_{hash(token.text)}"
                    self.graph_store.add_entity(
                        entity_id=concept_id,
                        name=token.text,
                        entity_type="CONCEPT",
                        properties={
                            "category": token.pos_,
                            "frequency": 1,  # 可以后续累计
                            "source_text": text[:50]
                        }
                    )
                    
                    # 建立词元到概念的关系
                    self.graph_store.add_relationship(
                        from_entity_id=token_id,
                        to_entity_id=concept_id,
                        relationship_type="REPRESENTS",
                        properties={"confidence": 1.0}
                    )
            
            # 建立词元之间的依存关系
            for token in doc:
                if token.is_punct or token.is_space or token.head == token:
                    continue
                    
                from_id = f"token_{hash(token.text + token.pos_)}"
                to_id = f"token_{hash(token.head.text + token.head.pos_)}"
                
                # Neo4j不允许关系类型包含冒号，需要清理
                relation_type = token.dep_.upper().replace(":", "_")
                
                self.graph_store.add_relationship(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_type=relation_type,  # 清理后的依存关系类型
                    properties={
                        "dependency": token.dep_,  # 保留原始依存关系
                        "source_text": text[:50]
                    }
                )
            
            logger.debug(f"🔗 已将词法分析结果存储到Neo4j: {len([t for t in doc if not t.is_punct and not t.is_space])} 个词元")
            
        except Exception as e:
            logger.warning(f"⚠️ 存储词法分析失败: {e}")

    def _extract_relations(self, text: str, entities: List[Entity]) -> List[Relation]:
        """提取关系"""
        relations = []
        # 仅保留简单共现关系，不做任何正则/关键词匹配
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i+1:]:
                relations.append(Relation(
                    from_entity=entity1.entity_id,
                    to_entity=entity2.entity_id,
                    relation_type="CO_OCCURS",
                    strength=0.5,
                    evidence=text[:100]
                ))
        return relations
    
    def _add_entity_to_graph(self, entity: Entity, memory_item: MemoryItem):
        """添加实体到Neo4j图数据库"""
        try:
            # 准备实体属性
            properties = {
                "name": entity.name,
                "description": entity.description,
                "frequency": entity.frequency,
                "memory_id": memory_item.id,
                "user_id": memory_item.user_id,
                "group_id": memory_item.group_id,
                **entity.properties
            }
            
            # 添加到Neo4j
            success = self.graph_store.add_entity(
                entity_id=entity.entity_id,
                name=entity.name,
                entity_type=entity.entity_type,
                properties=properties
            )
                    
            return success
            
        except Exception as e:
            logger.error(f"❌ 添加实体到图数据库失败: {e}")
            return False
        
    def _add_relation_to_graph(self, relation: Relation, memory_item: MemoryItem):
        """添加关系到Neo4j图数据库"""
        try:
            # 准备关系属性
            properties = {
                "strength": relation.strength,
                "memory_id": memory_item.id,
                "user_id": memory_item.user_id,
                "group_id": memory_item.group_id,
                "evidence": relation.evidence
            }
            
            # 添加到Neo4j
            success = self.graph_store.add_relationship(
                from_entity_id=relation.from_entity,
                to_entity_id=relation.to_entity,
                relationship_type=relation.relation_type,
                properties=properties
            )
                
            return success
            
        except Exception as e:
            logger.error(f"❌ 添加关系到图数据库失败: {e}")
            return False
        
    def _calculate_graph_relevance_neo4j(self, memory_metadata: Dict[str, Any], query_entities: List[Entity]) -> float:
        """计算Neo4j图相关性分数"""
        try:
            memory_entities = memory_metadata.get("entities", [])
            if not memory_entities or not query_entities:
                return 0.0
            
            # 实体匹配度
            query_entity_ids = {e.entity_id for e in query_entities}
            matching_entities = len(set(memory_entities).intersection(query_entity_ids))
            entity_score = matching_entities / len(query_entity_ids) if query_entity_ids else 0
            
            # 实体数量加权
            entity_count = memory_metadata.get("entity_count", 0)
            entity_density = min(entity_count / 10, 1.0)  # 归一化到[0,1]
            
            # 关系数量加权
            relation_count = memory_metadata.get("relation_count", 0)
            relation_density = min(relation_count / 5, 1.0)  # 归一化到[0,1]
            
            # 综合分数
            relevance_score = (
                entity_score * 0.6 +           # 实体匹配权重60%
                entity_density * 0.2 +         # 实体密度权重20%
                relation_density * 0.2         # 关系密度权重20%
            )
            
            return min(relevance_score, 1.0)
            
        except Exception as e:
            logger.debug(f"计算图相关性失败: {e}")
            return 0.0
    
    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[MemoryItem]:
        """检索语义记忆"""
        try:
            group_id = kwargs.get("group_id")

            # 1. 向量搜索
            vector_results = self._vector_search(query, top_k=top_k, group_id=group_id)
            
            # 2. 图搜索
            graph_results = self._graph_search(query, limit=top_k, group_id=group_id)

            # 3. 混合排序
            combined_results = self._combine_and_rank_results(
                vector_results, graph_results, query, top_k
            )

            # 3.1 对 combined_score 进行归一化
            scores = [r.get("combined_score", r.get("vector_score", 0.0)) for r in combined_results]
            if scores:
                import math
                max_s = max(scores)
                exps = [math.exp(s - max_s) for s in scores]
                denom = sum(exps) or 1.0
                probs = [e / denom for e in exps]
            else:
                probs = []

            # 4. 过滤已遗忘记忆并转换为MemoryItem
            result_memories = []
            for idx, result in enumerate(combined_results):
                # 处理时间戳
                timestamp = result.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except ValueError:
                        timestamp = datetime.now()
                elif isinstance(timestamp, (int, float)):
                    timestamp = datetime.fromtimestamp(timestamp)
                else:
                    timestamp = datetime.now()
                
                # 直接从结果数据构建MemoryItem（附带分数与概率）
                memory_item = MemoryItem(
                    id=result["id"],
                    content=result["content"],
                    memory_type="semantic",
                    user_id=result.get("user_id", "default"),
                    group_id=result.get("group_id", None),
                    timestamp=timestamp,
                    metadata={
                        **result.get("metadata", {}),
                        "combined_score": result.get("combined_score", 0.0),
                        "vector_score": result.get("vector_score", 0.0),
                        "graph_score": result.get("graph_score", 0.0),
                        "probability": probs[idx] if idx < len(probs) else 0.0,
                    }
                )
                result_memories.append(memory_item)
            
            logger.info(f"✅ 检索到 {len(result_memories)} 条相关记忆")
            return result_memories[:top_k]
                
        except Exception as e:
            logger.error(f"❌ 检索语义记忆失败: {e}")
            return []
            

    def _combine_and_rank_results(
        self,
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """结合向量和图搜索结果并重新排序"""
        # 合并结果，按内容去重
        combined = {}
        content_seen = set()

        # 添加向量结果
        for result in vector_results:
            memory_id = result["id"]
            content = result.get("content", "")

            # 内容去重
            content_hash = hash(content.strip())
            if content_hash in content_seen:
                logger.debug(f"跳过重复内容的向量结果: {content[:30]}...")
                continue

            content_seen.add(content_hash)
            combined[memory_id] = {
                **result,
                "content_hash": content_hash,
                "vector_score": result.get("score", 0.0),
                "graph_score": 0.0  # 默认图分数为0
            }

        # 添加图结果
        for result in graph_results:
            memory_id = result["id"]
            content = result.get("content", "")
            content_hash = hash(content.strip())

            if memory_id in combined:
                # 已存在，更新图分数
                combined[memory_id]["graph_score"] = result.get("similarity", 0.0)
            elif content_hash not in content_seen:
                content_seen.add(content_hash)
                combined[memory_id] = {
                    **result,
                    "content_hash": content_hash,
                    "vector_score": 0.0,  # 默认向量分数为0
                    "graph_score": result.get("similarity", 0.0)
                }

        # 计算混合分数
        for memory_id, result in combined.items():
            vector_score = result.get("vector_score", 0.0)
            graph_score = result.get("graph_score", 0.0)

            # 简单加权平均
            mixed_score = (vector_score * 0.7) + (graph_score * 0.3)
            
            result["debug_info"] = {
                "vector_score": vector_score,
                "graph_score": graph_score,
                "mixed_score": mixed_score
            }
            
            result["combined_score"] = mixed_score

        # 应用最小相关性阈值
        min_threshold = 0.1  # 最小相关性阈值
        filtered_results = [
            result for result in combined.values() 
            if result["combined_score"] >= min_threshold
        ]

        # 排序并返回
        sorted_results = sorted(
            filtered_results,
            key=lambda x: x["combined_score"],
            reverse=True
        )

        # 调试信息
        logger.debug(f"🔍 向量结果: {len(vector_results)}, 图结果: {len(graph_results)}")
        logger.debug(f"📝 去重后: {len(combined)}, 过滤后: {len(filtered_results)}")

        for i, result in enumerate(sorted_results[:3]):
            logger.debug(f"  结果{i+1}: 向量={result['vector_score']:.3f}, 图={result['graph_score']:.3f}, 精确={result.get('exact_match_bonus', 0):.3f}, 关键词={result.get('keyword_bonus', 0):.3f}, 公司={result.get('company_bonus', 0):.3f}, 实体={result.get('entity_type_bonus', 0):.3f}, 综合={result['combined_score']:.3f}")
        
        return sorted_results[:top_k]

    def update(
        self,
        memory_id: str,
        content: str = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """更新语义记忆（简单策略：删除后重建）"""
        try:
            # 1. 先查出旧记忆
            old = self._find_memory_by_id(memory_id)
            if not old:
                logger.warning(f"⚠️ 待更新记忆不存在: {memory_id}")
                return False

            # 2. 删除旧向量（图数据由重新 add 时覆盖/追加）
            try:
                # 依赖 QdrantVectorStore.delete_memories 按 payload.memory_id 删除
                if hasattr(self.vector_store, "delete_memories"):
                    self.vector_store.delete_memories([memory_id])
            except Exception as e:
                logger.warning(f"⚠️ 删除旧向量失败，继续尝试重建: {e}")

            # 3. 组装新的 MemoryItem
            new_content = content if content is not None else old.content
            new_metadata = dict(old.metadata or {})
            if metadata:
                new_metadata.update(metadata)

            new_item = MemoryItem(
                id=old.id,
                content=new_content,
                memory_type=old.memory_type,
                group_id=old.group_id,
                user_id=old.user_id,
                timestamp=datetime.now(),
                metadata=new_metadata,
            )

            # 4. 重新写入（向量 + 实体/关系）
            self.add(new_item)
            logger.info(f"✅ 更新语义记忆完成: {memory_id}")
            return True

        except Exception as e:
            logger.error(f"❌ 更新语义记忆失败 {memory_id}: {e}")
            return False
    
    def remove(self, memory_id: str) -> bool:
        """删除语义记忆：同时从向量库(Qdrant)和图数据库(Neo4j)中删除。

        Qdrant 侧按 payload.memory_id 删除；Neo4j 侧删除与该记忆相关的实体/关系。
        """
        success = True

        # 1）删除 Qdrant 中对应向量
        try:
            if self.vector_store is not None:
                # 优先使用按 memory_id 删除的接口，保持与 update/forget 语义一致
                if hasattr(self.vector_store, "delete_memories"):
                    self.vector_store.delete_memories([memory_id])
                elif hasattr(self.vector_store, "delete_vector"):
                    # 向后兼容旧的按 point-id 删除接口
                    self.vector_store.delete_vector([memory_id])
        except Exception as e:
            logger.warning(f"⚠️ 删除Qdrant向量失败: {e}")
            success = False

        # 2）删除 Neo4j 中与该记忆相关的实体/关系
        try:
            if self.graph_store is not None:
                # 删除所有 memory_id 匹配的实体节点（含其关系）
                query = """
                MATCH (e:Entity {memory_id: $memory_id})
                DETACH DELETE e
                """
                session = getattr(self.graph_store, "driver", None)
                database = getattr(self.graph_store, "database", "neo4j")
                if session is not None:
                    with session.session(database=database) as neo_session:
                        neo_session.run(query, memory_id=memory_id)
        except Exception as e:
            logger.warning(f"⚠️ 删除Neo4j实体失败: {e}")
            success = False

        if success:
            logger.info(f"✅ 已删除语义记忆: {memory_id}")
        else:
            logger.warning(f"⚠️ 语义记忆删除部分失败: {memory_id}")

        return success
        
    def has_memory(self, memory_id: str) -> bool:
        """检查记忆是否存在"""
        return self._find_memory_by_id(memory_id) is not None
    
    def clear(self):
        """清空所有语义记忆 - 包括专业数据库"""
        try:
            # 清空Qdrant向量数据库
            if self.vector_store:
                success = self.vector_store.clear_collection()
                if success:
                    logger.info("✅ Qdrant向量数据库已清空")
                else:
                    logger.warning("⚠️ Qdrant清空失败")
            
            # 清空Neo4j图数据库
            if self.graph_store:
                success = self.graph_store.clear_all()
                if success:
                    logger.info("✅ Neo4j图数据库已清空")
                else:
                    logger.warning("⚠️ Neo4j清空失败")
            
            logger.info("🧹 语义记忆系统已完全清空")
            
        except Exception as e:
            logger.error(f"❌ 清空语义记忆失败: {e}")
    
    def get_all(self) -> List[MemoryItem]:
        """获取所有语义记忆"""
        # 暂时不实现
        return []

    def get_stats(self) -> Dict[str, Any]:
        """获取语义记忆统计信息"""
        return {}

    def export_knowledge_graph(self) -> Dict[str, Any]:
        """导出知识图谱 - 从Neo4j获取统计信息"""
        try:
            # 从Neo4j获取统计信息
            stats = {}
            if self.graph_store:
                stats = self.graph_store.get_stats()
            
            return {
                "graph_stats": {
                    "total_nodes": stats.get("total_nodes", 0),
                    "entity_nodes": stats.get("entity_nodes", 0),
                    "memory_nodes": stats.get("memory_nodes", 0),
                    "total_relationships": stats.get("total_relationships", 0),
                }
            }
        except Exception as e:
            logger.error(f"❌ 导出知识图谱失败: {e}")
            return {
                "entities": {},
                "relations": [],
                "graph_stats": {"error": str(e)}
            }
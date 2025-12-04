from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import os
import math
import json

from loguru import logger

from ..base import BaseMemory, MemoryItem, MemoryConfig
from ..storage import SQLiteDocumentStore, QdrantVectorStore
from ..embedding import get_text_embedder, get_dimension

class EpisodicMemory(BaseMemory):
    """情景记忆实现"""
    def __init__(self, config: MemoryConfig, storage_backend=None):
        super().__init__(config, storage_backend)

        # 权威文档存储（SQLite）
        db_dir = self.config.storage_path if hasattr(self.config, 'storage_path') else "./memory_data"
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "memory.db")
        self.doc_store = SQLiteDocumentStore(db_path=db_path)

        # 统一嵌入模型（多语言，默认384维）
        self.embedder = get_text_embedder()

        # 向量存储（Qdrant - 使用连接管理器避免重复连接）
        from ..storage.qdrant_store import QdrantConnectionManager
        qdrant_url = os.getenv("QDRANT_URL", None)
        qdrant_api_key = os.getenv("QDRANT_API_KEY", None)
        self.vector_store = QdrantConnectionManager.get_instance(
            url=qdrant_url,
            api_key=qdrant_api_key,
            collection_name=os.getenv("QDRANT_COLLECTION", "memory_vectors"),
            vector_size=get_dimension(getattr(self.embedder, 'dimension', 384)),
            distance=os.getenv("QDRANT_DISTANCE", "cosine")
        )

        self.max_memory_age = timedelta(days=self.config.episodic_memory_retention_days)
        self.max_memory_capacity = self.config.episodic_memory_capacity

    def add(self, memory_item: MemoryItem) -> str:
        """添加情景记忆"""

        # 确保设置了整理状态，默认为 False (未整理)
        if "consolidated" not in memory_item.metadata:
            memory_item.metadata["consolidated"] = False

        # 1）权威存储（SQLite）
        ts_int = int(memory_item.timestamp.timestamp())
        self.doc_store.add_memory(
            memory_id=memory_item.id,
            user_id=memory_item.user_id,
            group_id=memory_item.group_id,
            content=memory_item.content,
            memory_type=self.memory_type,
            timestamp=ts_int,
            properties=memory_item.metadata,
        )

        # 2）向量存储（Qdrant）
        try:
            embedding = self.embedder.encode(memory_item.content)
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            
            self.vector_store.add_vector(
                vectors=[embedding],
                metadatas=[{
                    "memory_id": memory_item.id,
                    "memory_type": self.memory_type,
                    "user_id": memory_item.user_id,
                    "group_id": memory_item.group_id,
                    "content": memory_item.content
                }],
                ids=[memory_item.id]
            )
        except Exception as e:
            logger.error(f"[Memory] Failed to add vector for memory {memory_item.id}: {e}")
        
        return memory_item.id

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[MemoryItem]:
        """检索相关情景记忆"""
        user_id = kwargs.get("user_id", None)
        group_id = kwargs.get("group_id", None)
        time_range: Optional[Tuple[datetime, datetime]] = kwargs.get("time_range", None)

        candidate_ids: Optional[set] = None

        if time_range is not None:
            start_ts = int(time_range[0].timestamp())
            end_ts = int(time_range[1].timestamp())
            memories = self.doc_store.search_memories(
                user_id=user_id,
                group_id=group_id,
                memory_type=self.memory_type,
                start_time=start_ts,
                end_time=end_ts,
                limit=1000
            )
            candidate_ids = set(m["id"] for m in memories)

        # 向量搜索
        try:
            query_vec = self.embedder.encode(query)
            if hasattr(query_vec, 'tolist'):
                query_vec = query_vec.tolist()
            where = {'memory_type': self.memory_type}
            if user_id:
                where['user_id'] = user_id
            if group_id:
                where['group_id'] = group_id
            hits = self.vector_store.search_vectors(
                query=query_vec,
                top_k=top_k * 5,
                where=where
            )
        except Exception as e:
            hits = []

        # 过滤与重排
        now_ts = int(datetime.now().timestamp())
        results: List[Tuple[float, MemoryItem]] = []
        seen = set()
        for hit in hits:
            meta = hit.get("metadata", {})
            mem_id = meta.get("memory_id")
            if not mem_id or mem_id in seen:
                continue
            if candidate_ids is not None and mem_id not in candidate_ids:
                continue

            # 从权威库读取完整记录
            doc = self.doc_store.get_memory(mem_id)
            if not doc:
                continue

            # 计算综合性分数 向量0.7 + 近因0.3
            vector_score = float(hit.get("score", 0.0))
            age_days = max(0.0, (now_ts - int(doc["timestamp"])) / 86400.0)
            recency_score = 1.0 / (1.0 + age_days)

            combined = 0.7 * vector_score + 0.3 * recency_score

            item = MemoryItem(
                id=doc["memory_id"],
                content=doc["content"],
                memory_type=doc["memory_type"],
                user_id=doc["user_id"],
                group_id=doc["group_id"],
                timestamp=datetime.fromtimestamp(doc["timestamp"]),
                metadata={
                    **doc.get("properties", {}),
                    "relevance_score": combined,
                    "vector_score": vector_score,
                    "recency_score": recency_score
                }
            )

            results.append((combined, item))
            seen.add(mem_id)

        # 向量检索没有结果，回退到关键词匹配（基于 SQLite 文本搜索）
        if not results:
            # 从 SQLite 中拉一批候选（已按 user/group/time 过滤）
            start_ts = end_ts = None
            if time_range is not None:
                start_ts = int(time_range[0].timestamp())
                end_ts = int(time_range[1].timestamp())

            docs = self.doc_store.search_memories(
                user_id=user_id,
                group_id=group_id,
                memory_type=self.memory_type,
                start_time=start_ts,
                end_time=end_ts,
                limit=1000,
            )

            query_lower = query.lower()
            now_ts = int(datetime.now().timestamp())

            for doc in docs:
                content = doc.get("content", "")
                if query_lower not in content.lower():
                    continue

                ts = int(doc.get("timestamp", now_ts))
                age_days = max(0.0, (now_ts - ts) / 86400.0)
                recency_score = 1.0 / (1.0 + age_days)

                # 简单关键词匹配得分 + 近因权重
                keyword_score = 0.5
                base_relevance = keyword_score * 0.8 + recency_score * 0.2
                combined = base_relevance

                item = MemoryItem(
                    id=doc["id"],
                    content=content,
                    memory_type=doc["memory_type"],
                    user_id=doc["user_id"],
                    group_id=doc["group_id"],
                    timestamp=datetime.fromtimestamp(ts),
                    metadata={
                        "relevance_score": combined,
                        "recency_score": recency_score,
                        "source": "keyword_fallback",
                    },
                )
                results.append((combined, item))

        # 最终按综合得分排序并裁剪到 top_k
        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:top_k]]
    
    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新情景记忆"""
        # 1）更新权威存储（SQLite）
        doc_update = self.doc_store.update_memory(
            memory_id=memory_id,
            content=content,
            properties=metadata
        )

        # 2）更新向量存储（Qdrant）
        if content is not None:
            try:
                embedding = self.embedder.encode(content)
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()
                
                doc = self.doc_store.get_memory(memory_id)

                payload = {
                    "memory_id": memory_id,
                    "memory_type": self.memory_type,
                    "user_id": doc["user_id"],
                    "group_id": doc["group_id"],
                    "content": content
                }
                self.vector_store.add_vector(
                    vector_id=memory_id,
                    vector=embedding,
                    metadata=payload
                )
            except Exception as e:
                pass
        
        return doc_update
    
    def remove(self, memory_id: str) -> bool:
        """删除情景记忆"""
        # 1）删除权威存储（SQLite）
        doc_deleted = self.doc_store.delete_memory(memory_id)

        # 2）删除向量存储（Qdrant）
        try:
            self.vector_store.delete_vector(vector_id=memory_id)
        except Exception as e:
            pass

        return doc_deleted
    
    def has_memory(self, memory_id: str) -> bool:
        """检查情景记忆是否存在"""
        doc = self.doc_store.get_memory(memory_id)
        return doc is not None
    
    def clear(self) -> None:
        """清空所有情景记忆"""
        # 清空权威存储（SQLite）
        docs = self.doc_store.search_memories(memory_type="episodic", limit=10000)
        ids = [d["id"] for d in docs]
        for mid in ids:
            self.doc_store.delete_memory(mid)

        # Qdrant按ID删除对应向量
        try:
            if ids:
                self.vector_store.delete_memories(ids)
        except Exception:
            pass

    def forget(self) -> int:
        """情景记忆遗忘机制

        - 按保留天数删除过旧记忆
        - 按容量限制删除超出部分（优先删除最早的）
        返回被删除的记忆数量
        """
        # 检查最旧的一条记忆是否已整理
        # 如果最旧的记忆未整理，说明整理进度滞后，为防止丢失信息，暂停遗忘
        oldest_memories = self.doc_store.search_memories(
            memory_type=self.memory_type,
            limit=1,
            order_by="timestamp ASC"
        )
        
        if oldest_memories:
            oldest_mem = oldest_memories[0]
            props = oldest_mem.get("properties", {}) or {}
            # 默认为 False，如果未设置 consolidated
            if not props.get("consolidated", False):
                logger.debug(f"Skipping forget: Oldest memory {oldest_mem['id'][:8]} is not consolidated.")
                return 0

        forgotten_count = 0
        current_time = datetime.now()

        # 先拉取所有 episodic 记忆的概要信息
        docs = self.doc_store.search_memories(
            memory_type=self.memory_type,
            limit=self.max_memory_capacity * 2 if self.max_memory_capacity else 10000,
        )

        if not docs:
            return 0

        # 根据时间排序（最早在前）
        docs.sort(key=lambda d: int(d.get("timestamp", 0)))

        to_remove_ids: list[str] = []

        # 1）按时间阈值删除过旧记忆
        expire_before = current_time - self.max_memory_age
        expire_ts = int(expire_before.timestamp())

        for d in docs:
            ts = int(d.get("timestamp", 0))
            if ts and ts < expire_ts:
                to_remove_ids.append(d["id"])

        # 2）按容量限制删除多余记忆（在时间过滤之后）
        remaining_ids = [d["id"] for d in docs if d["id"] not in to_remove_ids]
        if self.max_memory_capacity and len(remaining_ids) > self.max_memory_capacity:
            overflow = len(remaining_ids) - self.max_memory_capacity
            # 由于 docs 已按时间排序，前面的就是最老的
            for mid in remaining_ids[:overflow]:
                to_remove_ids.append(mid)

        # 去重
        to_remove_ids = list(dict.fromkeys(to_remove_ids))

        # 执行删除：SQLite + Qdrant
        for mid in to_remove_ids:
            if self.remove(mid):
                forgotten_count += 1
                logger.info(f"Episodic memory forgotten: {mid[:8]}...")

        return forgotten_count
    
    def get_all(self) -> List[MemoryItem]:
        """获取所有情景记忆（谨慎使用，可能数据量大）"""
        docs = self.doc_store.search_memories(
            memory_type=self.memory_type,
            limit=10000
        )
        items = []
        for doc in docs:
            item = MemoryItem(
                id=doc["id"],
                content=doc["content"],
                memory_type=doc["memory_type"],
                user_id=doc["user_id"],
                group_id=doc["group_id"],
                timestamp=datetime.fromtimestamp(doc["timestamp"]),
                metadata=doc.get("properties", {}) or {},
            )
            items.append(item)
        return items
    
    def get_stats(self) -> Dict[str, Any]:
        db_stats = self.doc_store.get_database_stats()

        try:
            vs_stats = self.vector_store.get_collection_stats()
        except Exception:
            vs_stats = {"store_type": "qdrant"}

        return {
            "forgotten_count": 0,  # 硬删除模式下已遗忘的记忆会被直接删除
            # 使用 SQLite 统计的 episodic 记录数作为总量
            "total_count": db_stats.get("memory_count", 0),
            "time_span_days": self._calculate_time_span(),
            "memory_type": self.memory_type,
            "vector_store": vs_stats,
            "document_store": {k: v for k, v in db_stats.items() if k.endswith("_count") or k in ["store_type", "db_path"]}
        }

    def _calculate_time_span(self) -> float:
        """计算情景记忆时间跨度（天）

        基于 SQLite 中当前所有 episodic 记录的最早和最晚时间戳。
        若没有记录，则返回 0.0。
        """

        docs = self.doc_store.search_memories(
            memory_type=self.memory_type,
            limit=10000,
        )
        if not docs:
            return 0.0

        timestamps = [int(d.get("timestamp", 0)) for d in docs if d.get("timestamp") is not None]
        if not timestamps:
            return 0.0

        span_seconds = max(timestamps) - min(timestamps)
        # 转换为天，保留一位小数即可
        return span_seconds / 86400.0
    
    def get_unconsolidated_memories(self, limit: int = 10) -> List[MemoryItem]:
        """获取未整理（未转化为语义记忆）的情景记忆
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[MemoryItem]: 未整理的记忆列表
        """
        memories_data = self.doc_store.search_memories(
            filter_metadata={"consolidated": False},
            limit=limit,
            order_by="timestamp ASC"  # 优先处理最早的记忆
        )
        
        items = []
        for m in memories_data:
            items.append(MemoryItem(
                id=m["id"],
                content=m["content"],
                memory_type=m["memory_type"],
                group_id=m["group_id"],
                user_id=m["user_id"],
                timestamp=datetime.fromtimestamp(m["timestamp"]),
                metadata=m.get("properties", {}) or {}
            ))
        return items

    def count_unconsolidated_memories(self) -> int:
        """统计未整理的情景记忆数量"""
        return self.doc_store.count_memories(
            filter_metadata={"consolidated": False}
        )

    def mark_as_consolidated(self, memory_ids: List[str]):
        """标记记忆为已整理
        
        Args:
            memory_ids: 记忆ID列表
        """
        for mid in memory_ids:
            # 获取当前记忆以保留其他元数据
            memory = self.doc_store.get_memory(mid)
            if memory:
                props = memory.get("properties", {}) or {}
                props["consolidated"] = True
                self.doc_store.update_memory(mid, properties=props)
                logger.debug(f"Marked memory {mid} as consolidated")



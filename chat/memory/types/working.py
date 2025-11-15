from typing import List, Dict, Any
from datetime import datetime, timedelta

from ..base import BaseMemory, MemoryItem, MemoryConfig

class WorkingMemory(BaseMemory):
    """工作记忆
    
    用于存储实时记忆，使用滑动窗口，内部实现Python List
    """
    def __init__(self, config: MemoryConfig):
        self.max_capacity = config.working_memory_capacity or 10
        self.max_tokens = config.working_memory_tokens or 1000
        self.current_tokens = 0
        self.session_start = datetime.now()

        self.memories: List[MemoryItem] = []


    def add(self, memory_item: MemoryItem) -> str:
        """添加工作记忆"""
        self.memories.append(memory_item)

        # 更新当前Token数
        self.current_tokens += len(memory_item.content.split())

        # 检查容量限制
        self._enforce_capacity_limits()

        return memory_item.id
    
    def retrieve(self, query: str, limit: int = 5, group_id:str = None, user_id:str = None, **kwargs) -> List[MemoryItem]:
        """检索相关工作记忆"""
        if not self.memories:
            return []
        
        # 过滤已遗忘的记忆
        active_memories = [m for m in self.memories if not m.metadata.get("forgotten", False)]

        # 按用户ID过滤
        filtered_memories = active_memories
        if group_id is not None:
            filtered_memories = [m for m in filtered_memories if m.group_id == group_id]
        if user_id is not None:
            filtered_memories = [m for m in filtered_memories if m.user_id == user_id]
        
        return filtered_memories
    
    def update(
            self, 
            content: str,
            memory_id: str,
            metadata: Dict[str, Any] = None
        ) -> bool:
        """更新工作记忆"""
        for memory in self.memories:
            if memory.id == memory_id:
                old_tokens = len(memory.content.split())

                if content is not None:
                    memory.content = content
                    new_tokens = len(content.split())
                    self.current_tokens += (new_tokens - old_tokens)
                
                if metadata is not None:
                    memory.metadata.update(metadata)

                return True
        return False
    
    def remove(self, memory_id: str) -> bool:
        """删除工作记忆"""
        for i, memory in enumerate(self.memories):
            if memory.id == memory_id:
                self.current_tokens -= len(memory.content.split())
                self.current_tokens = max(0, self.current_tokens)
                del self.memories[i]
                return True
        return False
    
    def has_memory(self, memory_id: str) -> bool:
        """检查工作记忆是否存在"""
        return any(memory.id == memory_id for memory in self.memories)
    
    def clear(self):
        """清空工作记忆"""
        self.memories.clear()
        self.current_tokens = 0

    def get_stats(self) -> Dict[str, Any]:
        self._expire_old_memories()

        active_memories = self.memories

        return {
            "count": len(active_memories),
            "forgotten_count": 0,  # 工作记忆遗忘直接回被删除
            "total_count": len(self.memories),
            "current_tokens": self.current_tokens,
            "max_capacity": self.max_capacity,
            "max_tokens": self.max_tokens,
            "session_duration_minutes": (datetime.now() - self.session_start).total_seconds() / 60,
            "capacity_usage": len(active_memories) / self.max_capacity if self.max_capacity > 0 else 0.0,
            "token_usage": self.current_tokens / self.max_tokens if self.max_tokens > 0 else 0.0,
            "memory_type": "working" 
        }
    
    def get_recent(self, limit: int = 10) -> List[MemoryItem]:
        """获取最近的工作记忆"""
        sorted_memories = sorted(
            self.memories, 
            key=lambda x: x.timestamp, 
            reverse=True
        )
        return sorted_memories[:limit]
    
    def get_important(self, limit: int = 10) -> List[MemoryItem]:
        """获取重要的工作记忆"""
        return self.get_recent(limit)
    
    def get_all(self) -> List[MemoryItem]:
        """获取所有记忆"""
        return self.memories.copy()
    
    def forgot(self)-> int:
        """工作记忆遗忘机制"""
        self

    def _enforce_capacity_limits(self):
        """强制执行容量限制"""
        # 检查记忆数量限制
        while len(self.memories) > self.max_capacity:
            self._remove_lowest_priority_memory()
        
        # 检查token限制
        while self.current_tokens > self.max_tokens:
            self._remove_lowest_priority_memory()

    def _remove_lowest_priority_memory(self):
        """删除最久远的一条工作记忆并更新token计数"""
        if not self.memories:
            return

        # 找到时间最早的记忆并删除
        oldest_idx = min(range(len(self.memories)), key=lambda i: self.memories[i].timestamp)
        oldest = self.memories.pop(oldest_idx)

        # 更新当前Token数，确保不为负
        self.current_tokens -= len(oldest.content.split())
        self.current_tokens = max(0, self.current_tokens)
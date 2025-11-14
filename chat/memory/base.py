from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class MemoryItem(BaseModel):
    """记忆项数据结构"""
    id: str
    content: str
    memory_type: str
    group_id: str
    user_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True

class MemoryConfig(BaseModel):
    """记忆配置数据结构"""
    storage_path: str = "./data/memory_storage"

    # 工作记忆配置
    working_memory_capacity: int = 10  # 最大记忆容量

    # 情景记忆配置
    episodic_memory_retention_days: int = 30  # 情景记忆保留天数
    episodic_memory_capacity: int = 10000  # 情景记忆最大容量

class BaseMemory(ABC):
    """记忆基类"""
    
    def __init__(self, config: MemoryConfig, storage_backend=None):
        self.config = config
        self.storage = storage_backend
        self.memory_type = self.__class__.__name__.lower().replace("memory", "")

    @abstractmethod
    def add(self, memory_item: MemoryItem) -> str:
        """添加记忆项
        
        Args:
            memory_item (MemoryItem): 记忆项对象
            
        Returns:
            str: 记忆项ID
        """
        pass

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """检索相关记忆项
        
        Args:
            query (str): 查询字符串
            top_k (int): 返回的记忆项数量
            
        Returns:
            List[MemoryItem]: 相关记忆项列表
        """
        pass

    @abstractmethod
    def update(self, memory_id: str, content: str=None, metadata: Dict[str, Any]=None) -> bool:
        """更新记忆项
        
        Args:
            memory_id (str): 记忆项ID
            content (str, optional): 新内容
            metadata (Dict[str, Any], optional): 新元数据
            
        Returns:
            bool: 更新是否成功
        """
        pass

    @abstractmethod
    def remove(self, memory_id: str) -> bool:
        """删除记忆项
        
        Args:
            memory_id (str): 记忆项ID
            
        Returns:
            bool: 删除是否成功
        """
        pass

    @abstractmethod
    def has_memory(self, memory_id: str) -> bool:
        """检查记忆项是否存在
        
        Args:
            memory_id (str): 记忆项ID
            
        Returns:
            bool: 是否存在
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """清空所有记忆项"""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息
        
        Returns:
            Dict[str, Any]: 统计信息字典
        """
        pass

    def _generate_id(self) -> str:
        """生成唯一记忆项ID
        
        Returns:
            str: 唯一ID
        """
        import uuid
        return str(uuid.uuid4())
    
    def __str__(self):
        stats = self.get_stats()
        return f"<{self.__class__.__name__} type={self.memory_type} stats={stats}>"
    
    def __repr__(self):
        return self.__str__()
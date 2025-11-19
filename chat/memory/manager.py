from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import uuid

from loguru import logger

from .base import MemoryItem, MemoryConfig
from .types import WorkingMemory, EpisodicMemory, SemanticMemory

class MemoryManager:
    """记忆管理器 - 统一的记忆操作接口
    
    负责：
    - 初始化不同类型的记忆模块
    - 记忆生命周期管理
    - 记忆流动协调
    - 多类型记忆协调召回
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        group_id: str = "default_group",
        enable_working: bool = True,
        enable_episodic: bool = True,
        enable_semantic: bool = True,
    ):
        self.config = config or MemoryConfig()
        self.group_id = group_id

        # 初始化记忆模块
        self.memory_types: Dict[str, Union[WorkingMemory, EpisodicMemory, SemanticMemory]] = {}

        if enable_working:
            self.memory_types["working"] = WorkingMemory(
                config=self.config
            )

        if enable_episodic:
            self.memory_types["episodic"] = EpisodicMemory(
                config=self.config
            )
        
        if enable_semantic:
            self.memory_types["semantic"] = SemanticMemory(
                config=self.config
            )
        
        logger.info(f"MemoryManager初始化完成，启用记忆类型: {list(self.memory_types.keys())}")

    def add_memory(
        self,
        content: str,
        memory_type: str = "working",
        user_id: str = "default_user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        添加记忆项，返回记忆 ID
        
        :param content: 记忆内容
        :param memory_type: 记忆类型（working, episodic, semantic） 当前只支持插入working
        :param user_id: 用户 ID
        :param metadata: 额外元数据
        :return: 记忆 ID
        """
        memooy_item = MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            group_id=self.group_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        
        # 添加到对应的记忆类型
        if memory_type in self.memory_types:
            memory_id = self.memory_types[memory_type].add(memooy_item)
            logger.debug(f"添加记忆项到 {memory_type} 记忆，ID: {memory_id}")
        else:
            raise ValueError(f"不支持的记忆类型: {memory_type}")
        
    def retrieve_memory(
        self,
        query: str,
        memory_type: Optional[List[str]] = None,
        top_k: int = 5,
        time_range: Optional[tuple] = None,
    ) -> List[MemoryItem]:
        """
        检索记忆项
        
        :param query: 检索查询
        :param memory_type: 记忆类型
        :param top_k: 返回的记忆项数量
        :return: 记忆项列表
        """
        if memory_type is None:
            memory_type = list(self.memory_types.keys())
        
        all_results = {}
        per_type_limit = max(1, top_k // len(memory_type))
        
        for m_type in memory_type:
            if m_type in self.memory_types:
                memory_instance = self.memory_types[m_type]
                try:
                    type_results = memory_instance.retrieve(
                        query=query,
                        top_k=per_type_limit,
                        group_id=self.group_id
                    )
                    all_results[m_type] = type_results
                except Exception as e:
                    logger.error(f"从 {m_type} 记忆检索时出错: {e}")
                    continue
        
        return all_results
    
    
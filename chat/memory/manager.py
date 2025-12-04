from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import uuid
import json

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

        # 注册记忆流动回调
        self._register_forget_transfer()

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
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        
        # 添加到对应的记忆类型
        if memory_type in self.memory_types:
            memory_id = self.memory_types[memory_type].add(memooy_item)
            logger.debug(f"添加记忆项到 {memory_type} 记忆，ID: {memory_id}")
            return memory_id
        else:
            raise ValueError(f"不支持的记忆类型: {memory_type}")
        
    def retrieve_memory(
        self,
        query: str,
        memory_type: Optional[List[str]] = None,
        top_k: int = 5,
        time_range: Optional[tuple] = None,
    ) -> Dict[str, List[MemoryItem]]:
        """
        检索记忆项
        
        :param query: 检索查询
        :param memory_type: 记忆类型
        :param top_k: 返回的记忆项数量 (仅限制长期记忆)
        :return: 记忆项字典 {type: [items]}
        """
        if memory_type is None:
            memory_type = list(self.memory_types.keys())
        
        all_results = {}
        
        # 计算长期记忆类型的数量
        long_term_types = [t for t in memory_type if t != "working"]
        
        # 分配 top_k 给长期记忆
        per_type_limit = top_k
        if long_term_types:
            per_type_limit = max(1, top_k // len(long_term_types))
        
        for m_type in memory_type:
            if m_type in self.memory_types:
                memory_instance = self.memory_types[m_type]
                try:
                    # Working Memory 获取所有（传入较大 limit），其他类型使用分配的 limit
                    current_limit = 999 if m_type == "working" else per_type_limit
                    
                    type_results = memory_instance.retrieve(
                        query=query,
                        top_k=current_limit,
                        group_id=self.group_id
                    )
                    all_results[m_type] = type_results
                except Exception as e:
                    logger.error(f"从 {m_type} 记忆检索时出错: {e}")
                    continue
        
        return all_results
    
    def _register_forget_transfer(self):
        """注册工作记忆遗忘时转移到情景记忆的回调"""
        if "working" in self.memory_types and "episodic" in self.memory_types:
            working_memory: WorkingMemory = self.memory_types["working"]  # type: ignore
            episodic_memory: EpisodicMemory = self.memory_types["episodic"]  # type: ignore

            @working_memory.on_forget
            def transfer_to_episodic(item: MemoryItem):
                item.memory_type = "episodic"
                episodic_memory.add(item)
                logger.info(f"工作记忆遗忘，已转移到情景记忆，ID: {item.id}")
    
    async def consolidate_memories(self, llm_client: Any, limit: int = 10):
        """
        整理情景记忆到语义记忆（异步）
        
        :param llm_client: LLM 客户端实例 (需支持 .async_client.chat.completions.create)
        :param limit: 每次处理的记忆数量
        """
        if "episodic" not in self.memory_types or "semantic" not in self.memory_types:
            logger.warning("情景记忆或语义记忆未启用，无法进行整理")
            return

        episodic = self.memory_types["episodic"]
        semantic = self.memory_types["semantic"]

        # 1. 获取未整理的记忆
        memories = episodic.get_unconsolidated_memories(limit=limit)
        if not memories:
            return

        logger.info(f"开始批量整理 {len(memories)} 条情景记忆...")
        
        # 按群组分组处理，避免上下文混乱
        from collections import defaultdict
        memories_by_group = defaultdict(list)
        for mem in memories:
            memories_by_group[mem.group_id].append(mem)
            
        total_processed = 0
        
        for group_id, group_memories in memories_by_group.items():
            try:
                # 2. 构造该组的上下文
                context_lines = []
                current_source_ids = []
                for mem in group_memories:
                    ts_str = mem.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    context_lines.append(f"[{ts_str}] [User:{mem.user_id}]: {mem.content}")
                    current_source_ids.append(mem.id)
                
                context_text = "\n".join(context_lines)
                
                # 3. 调用 LLM 批量精炼
                prompt = f"""
你是一个记忆整理专家。请阅读以下按时间顺序排列的原始对话记忆片段，将它们重新组织、归纳为若干条独立的语义记忆。

任务要求：
1. **归纳与合并**：不要简单翻译每一句话。请根据语义主题，将分散在不同时间点的相关信息合并成一条完整的记忆。例如，用户分三次提到的考研计划细节，应整理为一条完整的考研计划记忆。
2. **数量自定**：根据内容丰富程度，自行决定生成多少条（n条）语义记忆。如果没有有价值的信息，可以返回空数组。
3. **内容精炼**：去除寒暄（如"你好"、"谢谢"）和无关废话。生成的 memory content 必须是客观、清晰的陈述句。
4. **重要性打分**：为每条记忆赋予一个重要性分数（importance，0.0-1.0），0.0表示微不足道，1.0表示极其重要（如关键事实、长期偏好）。

输入记忆片段：
{context_text}

请返回一个 JSON 对象，包含 "memories" 字段，格式如下：
{{
    "memories": [
        {{"content": "整理后的语义记忆内容1", "importance": 0.8}},
        {{"content": "整理后的语义记忆内容2", "importance": 0.3}}
    ]
}}
"""
                # 使用异步调用
                response = await llm_client.async_client.chat.completions.create(
                    model=llm_client.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content
                
                # 4. 解析 JSON
                facts = []
                try:
                    data = json.loads(result_text)
                    if isinstance(data, list):
                        facts = data
                    elif isinstance(data, dict):
                        # 尝试寻找列表值的字段，例如 {"facts": [...]}
                        for v in data.values():
                            if isinstance(v, list):
                                facts = v
                                break
                    
                    # 验证并标准化数据结构
                    valid_facts = []
                    for f in facts:
                        if isinstance(f, dict) and "content" in f:
                            # 确保 importance 是 float
                            try:
                                f["importance"] = float(f.get("importance", 0.5))
                            except (ValueError, TypeError):
                                f["importance"] = 0.5
                            valid_facts.append(f)
                        elif isinstance(f, str):
                            # 兼容纯字符串格式
                            valid_facts.append({"content": f, "importance": 0.5})
                    facts = valid_facts
                    
                except json.JSONDecodeError:
                    logger.warning(f"无法解析 LLM 返回的 JSON: {result_text[:100]}...")
                    continue

                # 5. 存入语义记忆
                if facts:
                    for item in facts:
                        content = item["content"]
                        importance = item["importance"]
                        
                        semantic_item = MemoryItem(
                            id=str(uuid.uuid4()),
                            content=content,
                            memory_type="semantic",
                            group_id=group_id,
                            user_id="system", # 归纳后的知识归属系统
                            timestamp=group_memories[-1].timestamp, # 使用最后一条的时间
                            metadata={
                                "source_episodic_ids": current_source_ids,
                                "consolidation_source": "batch_process",
                                "importance": importance
                            }
                        )
                        # 自动提取实体和关系
                        semantic.add(semantic_item)
                        logger.debug(f"生成语义记忆: {content[:20]}... (重要性: {importance})")
                else:
                    logger.info(f"群组 {group_id} 的记忆未提取到有效事实")

                # 6. 标记该组记忆为已整理 (无论是否提取出事实，都视为已处理)
                episodic.mark_as_consolidated(current_source_ids)
                total_processed += len(current_source_ids)

            except Exception as e:
                logger.error(f"整理群组 {group_id} 的记忆失败: {e}")
        
        if total_processed > 0:
            logger.info(f"成功整理 {total_processed} 条情景记忆")

    def get_unconsolidated_count(self) -> int:
        """获取未整理的情景记忆数量"""
        if "episodic" in self.memory_types:
            return self.memory_types["episodic"].count_unconsolidated_memories()
        return 0
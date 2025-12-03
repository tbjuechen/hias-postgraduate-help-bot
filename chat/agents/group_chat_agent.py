from typing import Optional, List, Any
from ..core.agent import Agent
from ..core.llm import LLMClient
from ..core.config import Config
from ..core.message import Message
from ..memory import MemoryManager, MemoryItem, MemoryConfig
from ..rag import RAGClient

class GroupChatAgent(Agent):
    def __init__(
        self, 
        name: str, 
        llm: LLMClient, 
        group_id: str, 
        system_prompt: Optional[str] = None, 
        config: Optional[Config] = None, 
        memory_config: Optional[MemoryConfig] = None,
        tools: Optional[List[Any]] = None,
        enable_memory: bool = True, 
        **kwargs
    ):
        super().__init__(name, llm, system_prompt, config)
        self.group_id = group_id
        self.tools = tools or []

        if enable_memory:
            # 使用传入的配置或默认配置
            mem_conf = memory_config or MemoryConfig()
            self.memory_manager = MemoryManager(
                config=mem_conf,
                group_id=group_id,
                enable_working=True,
                enable_episodic=True,
                enable_semantic=True
            )
        else:
            self.memory_manager = None

        self.rag_client = RAGClient()
    
    def _search_memory(
        self,
        query: str,
        memory_type: Optional[List[str]] = None
    ) -> dict:
        """
        记忆匹配查询
        
        :param query: 查询内容
        :param memory_type: 记忆类型列表，默认为所有类型
        :return: 匹配的记忆项字典
        """
        if not self.memory_manager:
            return {}
        
        results = self.memory_manager.retrieve_memory(
            query=query,
            memory_type=memory_type
        )
        return results
    
    def _default_prompt(self) -> str:
        return """
你是一个国科大杭州高等研究院研二在读的学姐，你非常乐于助人，喜欢和同学们分享学习经验和生活趣事。
你会根据同学们的问题，结合自己的经验，给出详细且有帮助的回答。
回复时语气亲切，富有耐心，像一个热心的学姐一样。
"""

    def _generate_system_prompt(
        self,
        query: str,
        top_k: int = 5,
        custom_prompt: Optional[str] = None
    ):
        related_memories = ""
        if self.memory_manager:
            # retrieve_memory 返回的是 Dict[str, List[MemoryItem]]
            memories_dict = self.memory_manager.retrieve_memory(
                query=query,
                memory_type=None,
                top_k=top_k
            )
            
            memory_lines = []
            for m_type, items in memories_dict.items():
                if items:
                    memory_lines.append(f"【{m_type}记忆】:")
                    for item in items:
                        memory_lines.append(f"- {item.content}")
            
            if memory_lines:
                related_memories = "\n".join(memory_lines)

        prompt = f"""
{self._default_prompt()}

相关记忆：
{related_memories}
"""
        # RAG client 上下文
        rag_contexts = self.rag_client.search_advanced(query)
        if rag_contexts:
            rag_lines = ["【外部知识】:"]
            for ctx in rag_contexts:
                rag_lines.append(f"- {ctx['content']}")
            prompt += "\n" + "\n".join(rag_lines) + "\n"

        if custom_prompt:
            prompt += f"\n{custom_prompt}"
        return prompt
    
    def add_memory(
        self,
        content: str,
        memory_type: str,
        user_id: str = "default_user",
        metadata: Optional[dict] = None
    ) -> str:
        """
        添加记忆项
        
        :param content: 记忆内容
        :param memory_type: 记忆类型
        :param user_id: 用户ID
        :param metadata: 额外元数据
        :return: 创建的记忆项
        """
        if not self.memory_manager:
            raise ValueError("Memory manager is not enabled.")
        
        memory_id = self.memory_manager.add_memory(
            content=content,
            memory_type=memory_type,
            user_id=user_id,
            metadata=metadata
        )
        return memory_id
    
    async def run(
        self,
        query: str,
        reply_string: Optional[list[str]] = None
    ) -> str:
        """
        处理输入的查询并返回响应

        :param query: 用户输入的查询
        :param reply_string: 可选的回复字符串列表，用于多轮对话
        :return: 生成的响应文本
        """

        # 2. 生成包含记忆上下文的 System Prompt
        system_prompt = self._generate_system_prompt(query)
        
        if reply_string:
            system_prompt += "\n下面是正在进行的对话：\n" + "\n".join(reply_string)
        
        messages = [
            Message(content=system_prompt, role="system"),
            Message(content=query, role="user")
        ]
    
        # 3. 调用 LLM
        response = await self.llm.achat(
            messages=messages
        )

        return response
import os
from typing import List, Dict, Optional, Union
from openai import OpenAI, AsyncOpenAI
from .message import Message


class LLMClient:
    """
    支持同步和异步调用的 LLM 客户端
    根据使用场景按需创建客户端，避免不必要的资源占用
    """
    
    def __init__(
        self, 
        model: str = None, 
        api_key: str = None, 
        base_url: str = None, 
        timeout: int = 30,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        初始化 LLM 客户端
        :param model: 模型名称
        :param api_key: API 密钥
        :param base_url: API 基础 URL
        :param timeout: 超时时间（秒）
        :param temperature: 温度参数
        :param max_tokens: 最大 token 数
        :param kwargs: 其他传递给 OpenAI 客户端的参数
        """
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.base_url = base_url or os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_kwargs = kwargs
        
        if not self.api_key:
            raise ValueError("必须提供 api_key 或设置 OPENAI_API_KEY 环境变量")
        
        # 延迟创建客户端，按需初始化
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
    
    @property
    def sync_client(self) -> OpenAI:
        """懒加载同步客户端"""
        if self._sync_client is None:
            self._sync_client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                **self.extra_kwargs
            )
        return self._sync_client
    
    @property
    def async_client(self) -> AsyncOpenAI:
        """懒加载异步客户端"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                **self.extra_kwargs
            )
        return self._async_client
    
    def _normalize_messages(self, messages: Union[List[Message], List[Dict[str, str]]]) -> List[Dict[str, str]]:
        """
        标准化消息格式，支持 Message 对象和字典
        :param messages: Message 对象列表或字典列表
        :return: 字典列表
        """
        if not messages:
            return []
        
        # 检查第一个元素类型
        if isinstance(messages[0], Message):
            return [msg.to_dict() for msg in messages]
        return messages
    
    def _build_request_params(self, messages: Union[List[Message], List[Dict[str, str]]], **overrides) -> Dict:
        """构建请求参数"""
        normalized_messages = self._normalize_messages(messages)
        params = {
            "model": self.model,
            "messages": normalized_messages,
            "temperature": self.temperature,
        }
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        params.update(overrides)
        return params
    
    def chat(
        self, 
        messages: Union[List[Message], List[Dict[str, str]]], 
        **kwargs
    ) -> str:
        """
        同步聊天接口
        :param messages: 消息列表，支持 Message 对象或字典 [{"role": "user", "content": "..."}]
        :param kwargs: 覆盖默认参数
        :return: 模型回复内容
        """
        params = self._build_request_params(messages, **kwargs)
        response = self.sync_client.chat.completions.create(**params)
        return response.choices[0].message.content.strip()
    
    async def achat(
        self, 
        messages: Union[List[Message], List[Dict[str, str]]], 
        **kwargs
    ) -> str:
        """
        异步聊天接口
        :param messages: 消息列表，支持 Message 对象或字典 [{"role": "user", "content": "..."}]
        :param kwargs: 覆盖默认参数
        :return: 模型回复内容
        """
        params = self._build_request_params(messages, **kwargs)
        response = await self.async_client.chat.completions.create(**params)
        return response.choices[0].message.content.strip()
    
    def simple_chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """
        简化的同步聊天接口
        :param system_prompt: 系统提示词
        :param user_message: 用户消息
        :param kwargs: 覆盖默认参数
        :return: 模型回复内容
        """
        messages = [
            Message(content=system_prompt, role="system"),
            Message(content=user_message, role="user")
        ]
        return self.chat(messages, **kwargs)
    
    async def asimple_chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """
        简化的异步聊天接口
        :param system_prompt: 系统提示词
        :param user_message: 用户消息
        :param kwargs: 覆盖默认参数
        :return: 模型回复内容
        """
        messages = [
            Message(content=system_prompt, role="system"),
            Message(content=user_message, role="user")
        ]
        return await self.achat(messages, **kwargs)
    
    def close(self):
        """关闭客户端连接"""
        if self._sync_client:
            self._sync_client.close()
        if self._async_client:
            # AsyncOpenAI 使用 aclose()，兼容无事件循环/有事件循环两种情况
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # 在已有事件循环中，调度关闭任务
                loop.create_task(self._async_client.close())
            else:
                # 无事件循环时，临时创建一个执行关闭
                asyncio.run(self._async_client.close())
    
    def __del__(self):
        """析构时清理资源"""
        try:
            self.close()
        except Exception:
            pass

    
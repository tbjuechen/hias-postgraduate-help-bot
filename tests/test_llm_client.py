import os
import sys
import asyncio

import pytest

from dotenv import load_dotenv

load_dotenv()

# 确保项目根目录能被导入
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chat.core.llm import LLMClient
from chat.core.message import Message


class FakeSyncClient:
    def __init__(self):
        self.last_params = None
        self.closed = False

    class Chat:
        class Completions:
            def __init__(self, outer):
                self._outer = outer

            def create(self, **params):
                # 记录调用参数并返回模拟响应结构
                self._outer.last_params = params

                class _Message:
                    def __init__(self, text):
                        self.content = text

                class _Choice:
                    def __init__(self, msg):
                        self.message = msg

                class _Resp:
                    def __init__(self, choice):
                        self.choices = [choice]

                return _Resp(_Choice(_Message("sync-reply")))

        def __init__(self, outer):
            self.completions = FakeSyncClient.Chat.Completions(outer)

    @property
    def chat(self):
        return FakeSyncClient.Chat(self)

    def close(self):
        self.closed = True


class FakeAsyncClient:
    def __init__(self):
        self.last_params = None
        self.closed = False

    class Chat:
        class Completions:
            def __init__(self, outer):
                self._outer = outer

            async def create(self, **params):
                self._outer.last_params = params

                class _Message:
                    def __init__(self, text):
                        self.content = text

                class _Choice:
                    def __init__(self, msg):
                        self.message = msg

                class _Resp:
                    def __init__(self, choice):
                        self.choices = [choice]

                return _Resp(_Choice(_Message("async-reply")))

        def __init__(self, outer):
            self.completions = FakeAsyncClient.Chat.Completions(outer)

    @property
    def chat(self):
        return FakeAsyncClient.Chat(self)

    async def close(self):
        self.closed = True


@pytest.mark.llm
@pytest.mark.parametrize("use_message_obj", [False, True])
def test_llm_client_chat_sync(monkeypatch, use_message_obj):
    """测试同步 chat() 使用 dict 或 Message 对象都能正常工作。"""
    monkeypatch.setenv("OPENAI_API_KEY", "DUMMY_KEY")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_BASE", "https://test.local")

    client = LLMClient()
    fake = FakeSyncClient()
    # 注入 fake sync client
    object.__setattr__(client, "_sync_client", fake)

    if use_message_obj:
        msgs = [Message(content="hello", role="user")]
    else:
        msgs = [{"role": "user", "content": "hello"}]

    resp = client.chat(msgs)

    assert resp == "sync-reply"
    # 确保参数被传过去
    assert fake.last_params is not None
    assert fake.last_params.get("model") == "test-model"


@pytest.mark.llm
def test_llm_client_chat_async_and_wrappers(monkeypatch):
    """测试异步聊天接口和简单封装 asimple_chat。"""
    monkeypatch.setenv("OPENAI_API_KEY", "DUMMY_KEY")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_BASE", "https://test.local")

    client = LLMClient()
    fake = FakeAsyncClient()
    object.__setattr__(client, "_async_client", fake)

    # 直接调用 achat via asyncio.run
    msg = Message(content="ping", role="user")
    resp = asyncio.run(client.achat([msg]))
    assert resp == "async-reply"

    # simple_chat 同步包装应工作（会调用 sync client）
    # 为此注入 sync fake
    fake_sync = FakeSyncClient()
    object.__setattr__(client, "_sync_client", fake_sync)
    simple = client.simple_chat("system prompt", "question")
    assert simple == "sync-reply"

    # asimple_chat 使用 asyncio.run 包装
    resp2 = asyncio.run(client.asimple_chat("sys", "q"))
    assert resp2 == "async-reply"


@pytest.mark.llm
def test_llm_client_close_calls_underlying(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "DUMMY_KEY")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_BASE", "https://test.local")

    client = LLMClient()
    fake_sync = FakeSyncClient()
    fake_async = FakeAsyncClient()
    object.__setattr__(client, "_sync_client", fake_sync)
    object.__setattr__(client, "_async_client", fake_async)

    client.close()

    assert fake_sync.closed is True
    # async fake close is called via asyncio.run inside close()
    assert fake_async.closed is True


@pytest.mark.llm
def test_llm_client_real_call():
    """实际调用外部 LLM 接口，验证能正常返回文本。

    依赖 OPENAI_API_KEY / OPENAI_MODEL / OPENAI_API_BASE 配置正确，
    否则在本地没有配置时应自动跳过。
    """

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")

    if not api_key or not model:
        pytest.skip("缺少 OPENAI_API_KEY 或 OPENAI_MODEL，跳过真实 LLM 调用测试")

    client = LLMClient()
    text = client.simple_chat("你是一个测试助手", "打个招呼")

    assert isinstance(text, str)
    assert len(text.strip()) > 0

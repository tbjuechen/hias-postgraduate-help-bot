import os
import sys
import asyncio
from typing import List

import pytest

from dotenv import load_dotenv

load_dotenv()

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chat.memory.embedding import OpenAIEmbeddingModel  # noqa: E402

@pytest.mark.embedding
def test_openai_embedding_sync_single(monkeypatch):
    """测试 OpenAIEmbeddingModel 同步 encode 单条文本。

    通过 monkeypatch 替换内部 sync_client，避免真实调用外部 API。
    """

    # 设置环境变量，模拟真实配置
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding-model")
    monkeypatch.setenv("EMBEDDING_API_KEY", "DUMMY_KEY")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://test.local")

    class FakeResponse:
        def __init__(self, embeddings: List[List[float]]):
            class _Item:
                def __init__(self, emb):
                    self.embedding = emb

            class _Data(list):
                pass

            self.data = _Data(_Item(e) for e in embeddings)

    class FakeSyncClient:
        def __init__(self):
            self.called = False
            self.last_model = None
            self.last_input = None

        class _Embeddings:
            def __init__(self, outer):
                self._outer = outer

            def create(self, model, input):  # type: ignore[override]
                self._outer.called = True
                self._outer.last_model = model
                self._outer.last_input = input
                # 返回固定维度的 embedding
                return FakeResponse([[0.1, 0.2, 0.3]])

        @property
        def embeddings(self):
            return FakeSyncClient._Embeddings(self)

    # 构造模型实例，走环境变量逻辑
    model = OpenAIEmbeddingModel()

    fake_client = FakeSyncClient()
    # 替换内部 sync_client
    object.__setattr__(model, "_sync_client", fake_client)

    vec = model.encode("hello")

    assert fake_client.called is True
    assert fake_client.last_model == "test-embedding-model"
    assert fake_client.last_input == ["hello"]
    assert isinstance(vec, list)
    assert vec == [0.1, 0.2, 0.3]
    assert model.dimension == 3


@pytest.mark.embedding
def test_openai_embedding_real_call():
    """实际调用外部 embedding 接口，验证能正常返回向量。

    依赖环境变量 EMBEDDING_MODEL / EMBEDDING_API_KEY / EMBEDDING_BASE_URL 已正确配置，
    否则本测试会失败。建议在本地手动跑、CI 中按需跳过。
    """

    model = OpenAIEmbeddingModel()

    text = "hello world"
    vec = model.encode(text)

    # 基本健壮性检查：有返回、为 list、长度大于 0
    assert isinstance(vec, list)
    assert len(vec) > 0


@pytest.mark.embedding
def test_openai_embedding_async_many(monkeypatch):
    """测试 OpenAIEmbeddingModel 异步 aencode 多条文本（通过 asyncio.run 包装）。"""

    # 设置环境变量，模拟真实配置
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding-model")
    monkeypatch.setenv("EMBEDDING_API_KEY", "DUMMY_KEY")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://test.local")

    class FakeResponse:
        def __init__(self, embeddings: List[List[float]]):
            class _Item:
                def __init__(self, emb):
                    self.embedding = emb

            class _Data(list):
                pass

            self.data = _Data(_Item(e) for e in embeddings)

    class FakeAsyncClient:
        def __init__(self):
            self.called = False
            self.last_model = None
            self.last_input = None

        class _Embeddings:
            def __init__(self, outer):
                self._outer = outer

            async def create(self, model, input):  # type: ignore[override]
                self._outer.called = True
                self._outer.last_model = model
                self._outer.last_input = input
                # 返回两条 embedding
                return FakeResponse([[1.0, 0.0], [0.0, 1.0]])

        @property
        def embeddings(self):
            return FakeAsyncClient._Embeddings(self)

    model = OpenAIEmbeddingModel()

    fake_client = FakeAsyncClient()
    object.__setattr__(model, "_async_client", fake_client)

    texts = ["a", "b"]
    # 使用 asyncio.run 调用异步接口
    vecs = asyncio.run(model.aencode(texts))

    assert fake_client.called is True
    assert fake_client.last_model == "test-embedding-model"
    assert fake_client.last_input == texts
    assert isinstance(vecs, list)
    assert len(vecs) == 2
    assert vecs[0] == [1.0, 0.0]
    assert vecs[1] == [0.0, 1.0]
    assert model.dimension == 2

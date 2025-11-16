from typing import List, Union, Optional
import threading
import os
import numpy as np
from openai import OpenAI, AsyncOpenAI

class EmbeddingModel:
    """嵌入模型基类"""

    def encode(self, texts: Union[str, List[str]]):
        raise NotImplementedError()
    
    @property
    def dimension(self) -> int:
        raise NotImplementedError()
    

class TFIDFEmbeddingModel(EmbeddingModel):
    """基于TF-IDF的简单嵌入模型"""

    def __init__(self, max_features: int = 1000, **kwargs):
        self.max_features = max_features
        self._vectorizer = None
        self._is_fitted = False
        self._dimension = max_features
        self._init_vectorizer()

    def _init_vectorizer(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._vectorizer = TfidfVectorizer(max_features=self.max_features, stop_words='english')
        except ImportError:
            raise ImportError("请安装 scikit-learn: pip install scikit-learn")
        
    def fit(self, texts: List[str]):
        """拟合TF-IDF向量化器"""
        self._vectorizer.fit(texts)
        self._is_fitted = True
        self._dimension = len(self._vectorizer.get_feature_names_out())

    def encode(self, text: List[str]):
        if not self._is_fitted:
            raise ValueError("TF-IDF向量化器尚未拟合，请先调用 fit 方法。")
        if isinstance(text, str):
            text = [text]
            single = True
        else: 
            single = False
        
        tfidf_matrix = self._vectorizer.transform(text)
        embeddings = tfidf_matrix.toarray()
        if single:
            return embeddings[0]
        return [e for e in embeddings]
    
    @property
    def dimension(self) -> int:
        return self._dimension


class OpenAIEmbeddingModel(EmbeddingModel):
    """使用 OpenAI 兼容 API 的嵌入模型"""

    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        timeout: int = 30,
        **kwargs,
    ):
        """初始化嵌入模型

        :param model: 模型名称，默认从 EMBEDDING_MODEL 环境变量读取
        :param api_key: API 密钥，默认从 EMBEDDING_API_KEY 环境变量读取
        :param base_url: API 基础 URL，默认从 EMBEDDING_BASE_URL 环境变量读取
        :param timeout: 超时时间（秒）
        :param kwargs: 其他透传给 AsyncOpenAI 的参数
        """
        self.model = model or os.getenv("EMBEDDING_MODEL", "volcengine-text-embedding-001")
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY")
        self.base_url = base_url or os.getenv("EMBEDDING_BASE_URL", "https://api.volcengine.com")
        self.timeout = timeout
        self.extra_kwargs = kwargs

        if not self.api_key:
            raise ValueError("必须设置 EMBEDDING_API_KEY 来启用文本嵌入功能")

        # 同步客户端在初始化时就创建，异步客户端懒加载
        self._sync_client: OpenAI = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            **self.extra_kwargs,
        )
        self._async_client: Optional[AsyncOpenAI] = None
        # 维度：优先在初始化时通过一次轻量嵌入获取
        self._dimension: Optional[int] = None


    @property
    def sync_client(self) -> OpenAI:
        """同步客户端（在 __init__ 中已创建）。"""
        return self._sync_client

    @property
    def async_client(self) -> AsyncOpenAI:
        """懒加载异步客户端"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                **self.extra_kwargs,
            )
        return self._async_client

    async def _encode_one(self, text: str):
        """编码单条文本，返回一维向量(list[float])"""
        resp = await self.async_client.embeddings.create(model=self.model, input=[text])
        emb = resp.data[0].embedding
        if self._dimension is None:
            self._dimension = len(emb)
        return emb

    async def _encode_many(self, texts: List[str]):
        resp = await self.async_client.embeddings.create(model=self.model, input=texts)
        embs = [item.embedding for item in resp.data]
        if self._dimension is None and embs:
            self._dimension = len(embs[0])
        return embs

    async def aencode(self, texts: Union[str, List[str]]):
        """异步编码接口

        :param texts: 单条字符串或字符串列表
        :return: 若输入为 str，返回 list[float]；若输入为 list[str]，返回 list[list[float]]
        """
        if isinstance(texts, str):
            return await self._encode_one(texts)
        return await self._encode_many(texts)

    def encode(self, texts: Union[str, List[str]]):
        """同步编码接口（直接使用同步 OpenAI 客户端）"""

        if isinstance(texts, str):
            resp = self.sync_client.embeddings.create(model=self.model, input=[texts])
            emb = resp.data[0].embedding
            # 首次同步嵌入时记录向量维度
            if self._dimension is None:
                self._dimension = len(emb)
            return emb

        # 多条文本
        resp = self.sync_client.embeddings.create(model=self.model, input=texts)
        embs = [item.embedding for item in resp.data]
        # 也可以通过多条文本的首个向量来初始化维度
        if self._dimension is None and embs:
            self._dimension = len(embs[0])
        return embs

    @property
    def dimension(self) -> int:
        """向量维度（首次调用 encode/aencode 后才会被确定）"""
        if self._dimension is None:
            # 尝试做一次极简嵌入来初始化维度；失败则保持懒加载
            try:
                resp = self._sync_client.embeddings.create(
                    model=self.model,
                    input=["init"],
                )
                emb = resp.data[0].embedding
                if emb:
                    self._dimension = len(emb)
            except Exception:
                # 不影响后续使用，维度仍会在首次 encode/aencode 时推断
                pass
        return self._dimension
    
def create_embedding_model(model_type: str = "openai", **kwargs) -> EmbeddingModel:
    """根据模型类型创建嵌入模型实例

    :param model_type: 嵌入模型类型，支持 "openai" 和 "tfidf"
    :return: EmbeddingModel 实例
    """
    if model_type == "openai":
        return OpenAIEmbeddingModel(**kwargs)
    elif model_type == "tfidf":
        return TFIDFEmbeddingModel(**kwargs)
    else:
        raise ValueError(f"不支持的嵌入模型类型: {model_type}")
    
def create_embedding_model_with_fallback(
    preferred_type: str = "openai", 
    **kwargs,
) -> EmbeddingModel:
    """带回退的创建：openai -> tfidf

    :param preferred_type: 首选嵌入模型类型，当前支持 "openai" 和 "tfidf"
    :param kwargs: 传给 create_embedding_model 的额外参数
    """
    # 当前支持的类型列表
    fallback = ["openai", "tfidf"]

    # 如果首选在列表里，就提到最前面
    if preferred_type in fallback:
        fallback.remove(preferred_type)
        fallback.insert(0, preferred_type)

    # 依次尝试可用的模型类型
    last_err: Exception | None = None
    for t in fallback:
        try:
            return create_embedding_model(t, **kwargs)
        except Exception as e:
            last_err = e
            continue

    # 如果都失败了，抛更友好的错误
    raise RuntimeError(
        f"所有嵌入模型都不可用，请检查配置或依赖。最后错误: {last_err}"
    )

_lock = threading.RLock()
_embedder:Optional[EmbeddingModel] = None

def _build_embedder() -> EmbeddingModel:
    preferred = os.getenv("EMBED_MODEL_TYPE", "openai")
    defaults_model = "volcengine-text-embedding-001"
    model_name = os.getenv("EMBEDDING_MODEL", defaults_model)

    kwargs = {}
    if model_name:
        kwargs["model"] = model_name
    
    api_key = os.getenv("EMBEDDING_API_KEY")
    if api_key:
        kwargs["api_key"] = api_key
    base_url = os.getenv("EMBEDDING_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return create_embedding_model_with_fallback(preferred, **kwargs)

def get_text_embedder() -> EmbeddingModel:
    """获取全局共享的文本嵌入实例（线程安全单例）"""
    global _embedder
    if _embedder is not None:
        return _embedder
    with _lock:
        if _embedder is None:
            _embedder = _build_embedder()
        return _embedder


def get_dimension(default: int = 384) -> int:
    """获取统一向量维度（失败回退默认值）"""
    try:
        return int(getattr(get_text_embedder(), "dimension", default))
    except Exception:
        return int(default)


def refresh_embedder() -> EmbeddingModel:
    """强制重建嵌入实例（可用于动态切换环境变量）"""
    global _embedder
    with _lock:
        _embedder = _build_embedder()
        return _embedder
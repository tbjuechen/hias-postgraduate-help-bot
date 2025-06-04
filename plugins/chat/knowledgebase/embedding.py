"""
embedding with volcengine API use openai API
"""
import os
from openai import AsyncOpenAI

# 从环境变量中加载配置
base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.volcengine.com")
api_key = os.getenv("EMBEDDING_API_KEY", None)
if not api_key:
    raise ValueError("必须设置 EMBEDDING_API_KEY 来启用文本嵌入功能")
model = os.getenv("EMBEDDING_MODEL", "volcengine-text-embedding-001")

client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url,
)

def embedding(text: str):
    response = client.embeddings.create(
        model=model,
        input=[text],
    )
    return response.data[0].embedding

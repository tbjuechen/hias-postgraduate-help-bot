import os
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from chat.rag.client import RAGClient
from loguru import logger

def main():
    # 初始化 RAG 客户端
    rag_client = RAGClient(namespace="hias_docs")
    
    # 定义文档目录
    docs_dir = os.path.join(project_root, "src", "docs")
    
    if not os.path.exists(docs_dir):
        logger.error(f"文档目录不存在: {docs_dir}")
        return

    # 获取所有支持的文件
    files_to_add = []
    for root, _, files in os.walk(docs_dir):
        for file in files:
            # 过滤掉隐藏文件
            if file.startswith('.'):
                continue
            
            file_path = os.path.join(root, file)
            # 简单检查一下扩展名，具体支持由 RAGClient 内部判断
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.pdf', '.md', '.txt', '.docx']:
                files_to_add.append(file_path)
    
    if not files_to_add:
        logger.warning("没有找到需要添加的文档")
        return

    logger.info(f"找到 {len(files_to_add)} 个文档，开始添加到知识库...")
    
    try:
        # 添加文档
        num_chunks = rag_client.add_documents(files_to_add)
        logger.info(f"成功添加文档，共生成 {num_chunks} 个文本块")
        
        # 打印统计信息
        stats = rag_client.get_stats()
        logger.info(f"当前知识库统计: {stats}")
        
    except Exception as e:
        logger.error(f"添加文档失败: {e}")

if __name__ == "__main__":
    main()
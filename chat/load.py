import json
import asyncio

from .knowledgebase import qa_base, doc_base

from pathlib import Path

from nonebot import logger

SRC_DIR = Path('src') / 'json'
QA_PATH = SRC_DIR / 'QA'
DOC_PATH = SRC_DIR / 'doc'

def build_qa_base():
    """
    根据当前目录下的QA文件夹中的json文件构建问答知识库
    """
    pass

def build_doc_base():
    """
    根据当前目录下的doc文件夹中的json文件构建文档知识库
    """
    # 遍历doc文件夹中的所有json文件
    for file in DOC_PATH.glob('*.json'):
        # 排除exsample.json文件
        if file.name == 'example.json':
            continue
        with open(file, 'r', encoding='utf-8') as f:
            data = f.read()
            # 解析json数据
            doc_data = json.loads(data)

            # metadata = doc_data.get('metadata', {})
            # if 'tags' in metadata:
            #     metadata['tags'] = str(metadata['tags'])

            metadata = {}
            # 添加到文档知识库
            doc_base.add(title=doc_data['title'], content=doc_data['content'], metadata=metadata)

    logger.info(f"文档知识库已加载，包含 {len(doc_base.collection.get()['ids'])} 个文档。")
    # test 
    result = asyncio.run(doc_base.query("测试文档", n_results=1))
    logger.info(f"查询文档知识库结果：{result}")
    
from .vdb import BaseCollection, Item

from datetime import datetime

class QACollection(BaseCollection):
    """
    问答记录数据库，用于few-shot学习和知识库问答。
    存储逻辑：
    - ids: 问题的文本内容
    - documents: 问题的回复内容
    - embedding: 问题文本的向量表示
    - metadata: 附加的元数据（如创建时间、标签等)
    """
    def __init__(self, name: str = "qa_collection"):
        super().__init__(name)
        self.name = name

    def add(self, question: str, answer: str, metadata:dict=None):
        """
        添加问答对到数据库

        :param question: 问题文本
        :param answer: 回答文本
        :param metadata: 附加的元数据
        """
        if not metadata:
            metadata = {}
        
        metadata['created_at'] = datetime.now().isoformat()

        item = Item(ids=question, documents=answer, metadata=metadata)
        self._add(item)

    def query(self, question: str, n_results: int = 1):
        """
        查询问答对

        :param question: 查询问题
        :param n_results: 返回的结果数量
        :return: 查询结果
        """
        return super().query(question, n_results=n_results)
    
class DocumentCollection(BaseCollection):
    """
    文档存储数据库，用于存储和检索文档内容。

    存储逻辑：
    - ids: 文档标题+分片号(如果分片)
    - documents: 文档内容
    - embedding: 文档内容的向量表示
    - metadata: 附加的元数据（如创建时间、标签等)
    """
    def __init__(self, name: str = "document_collection"):
        super().__init__(name)
        self.name = name

    def add(self, doc_id: str, content: str, metadata:dict=None):
        """
        添加文档到数据库

        :param doc_id: 文档唯一标识符
        :param content: 文档内容
        :param metadata: 附加的元数据
        """
        if not metadata:
            metadata = {}
        
        metadata['created_at'] = datetime.now().isoformat()

        item = Item(ids=doc_id, documents=content, metadata=metadata)
        self._add(item)

    def query(self, doc_id: str, n_results: int = 1):
        """
        查询文档

        :param doc_id: 查询文档的唯一标识符
        :param n_results: 返回的结果数量
        :return: 查询结果
        """
        return super().query(doc_id, n_results=n_results)
    
from .text_splitter import RecursiveCharacterTextSplitter
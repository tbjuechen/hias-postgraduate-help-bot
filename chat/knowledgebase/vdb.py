'''
vector database api
'''
import chromadb
from pathlib import Path
from typing import Callable
from abc import ABC, abstractmethod

import asyncio

from .embedding import embedding

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "chromadb"

client = chromadb.PersistentClient(path=str(DB_FILE), settings=chromadb.Settings(anonymized_telemetry=False))

class Item:
    def __init__(self,ids:str ,documents:str ,embedding:Callable=embedding, metadata:dict=None):
        self.ids = ids
        self.documents = documents
        self.embedding = asyncio.create_task(embedding(ids))
        self.metadata = metadata if metadata else {}

    def to_dict(self):
        return {
            'ids': self.ids,
            'documents': self.documents,
            'embeddings': self.embedding,
            'metadatas': self.metadata
        }
    
class BaseCollection(ABC):
    def __init__(self, name:str, client:chromadb.PersistentClient=client):
        self.name = name
        self.client:chromadb.ClientAPI = client
        self.collection:chromadb.Collection = self.client.get_or_create_collection(name, metadata={
            'hnsw:space': 'cosine',})

    def _add(self, item:Item):
        # check if id already exists
        self.get(ids=item.ids)
        if len(self.collection.get(ids=item.ids)['ids']) > 0:
            raise ValueError(f"Item with id {item.ids} already exists in the collection.")
        self.collection.add(**item.to_dict())

    def _query(self, query_embedding, n_results:int=1):
        return self.collection.query(query_embedding, n_results=n_results)
    
    def _delete(self, ids:str):
        self.collection.delete(ids=ids)
    
    def add(self, item:Item):
        self._add(item)

    async def query(self, query:str, n_results:int=1):
        return self._query(await embedding(query), n_results=n_results)
    
    def delete(self, ids:str):
        self._delete(ids)

    def get(self, **kwargs):
        kwargs['include'] = ['embeddings', 'documents', 'metadatas'] if 'include' not in kwargs else kwargs['include']
        return self.collection.get(**kwargs)
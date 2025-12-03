from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import sqlite3
import json
import os
import threading

from loguru import logger

class DocumentStore(ABC):
    """文档存储基类"""

    @abstractmethod
    def add_memory(
        self,
        memory_id: str,
        user_id: str,
        group_id: str,
        content: str,
        memory_type: str,
        timestamp: int,
        properties: Dict[str, Any] = None
    ):
        """添加记忆文档"""
        pass

    @abstractmethod
    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取记忆文档"""
        pass

    @abstractmethod
    def search_memories(
        self,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索记忆文档"""
        pass

    @abstractmethod
    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新记忆文档"""
        pass

    @abstractmethod
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆文档"""
        pass

    @abstractmethod
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        pass

class SQLiteDocumentStore(DocumentStore):
    """SQLite实现的文档存储"""

    _instances = {}
    _initialized_dbs = set()

    def __new__(cls, db_path: str):
        abs_path = os.path.abspath(db_path)
        if abs_path not in cls._instances:
            instance = super(SQLiteDocumentStore, cls).__new__(cls)
            cls._instances[abs_path] = instance
        return cls._instances[abs_path]
    
    def __init__(self, db_path: str):
        if hasattr(self, '_initialized'):
            return
        
        self.db_path = db_path
        self.local = threading.local()

        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        abs_path = os.path.abspath(db_path)
        if abs_path not in self._initialized_dbs:
            self._init_database()
            self._initialized_dbs.add(abs_path)
            logger.info(f"[OK✅] Initialized SQLiteDocumentStore at {db_path}")

        self._initialized = True
    
    @property
    def connection(self) -> sqlite3.Connection:
        """
        线程本地的 SQLite 连接（懒加载）
        每个线程第一次访问时创建自己的连接
        """
        if not hasattr(self.local, "connection"):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self.local.connection = conn
        return self.local.connection
    
    def _init_database(self):
        """初始化数据库表"""
        conn = self.connection
        cursor = conn.cursor()

        # 创建群组表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT,            
                properties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建记忆表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                timestamp INTEGER,
                properties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups(id)
            )
        """)

        # 创建索引
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories (memory_type)",
            "CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories (timestamp)",
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)
        
        conn.commit()
        logger.info(f"[OK✅] SQLite tables and indexes initialized.")

    def add_memory(
        self,
        memory_id: str,
        user_id: str,
        group_id: str,
        content: str,
        memory_type: str,
        timestamp: int,
        properties: Dict[str, Any] = None
    ):
        """添加记忆文档"""
        conn = self.connection
        cursor = conn.cursor()

        # 群组是否存在
        cursor.execute('INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)', (group_id, group_id))

        # 插入记忆
        cursor.execute("""
            INSERT OR REPLACE INTO memories
            (id, user_id, group_id, content, memory_type, timestamp, properties, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            memory_id,
            user_id,
            group_id,
            content,
            memory_type,
            timestamp,
            json.dumps(properties) if properties else None
        ))

        conn.commit()
        return memory_id
    
    def get_memory(self, memory_id) -> Optional[Dict[str, Any]]:
        """获取记忆文档"""
        conn = self.connection
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, group_id, content, memory_type, timestamp, properties, created_at
            FROM memories 
            WHERE id = ?
        """, (memory_id,))

        row = cursor.fetchone()
        if row:
            memory = dict(row)
            if memory.get("properties"):
                memory["properties"] = json.loads(memory["properties"])
            return memory
        return None
    
    def search_memories(
        self,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 10,
        order_by: str = "timestamp DESC",
        filter_metadata: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """搜索记忆文档"""
        conn = self.connection
        cursor = conn.cursor()

        # 构建查询条件
        where_conditions = []
        params = []
        
        if user_id:
            where_conditions.append("user_id = ?")
            params.append(user_id)
        
        if group_id:
            where_conditions.append("group_id = ?")
            params.append(group_id)
        
        if memory_type:
            where_conditions.append("memory_type = ?")
            params.append(memory_type)
        
        if start_time:
            where_conditions.append("timestamp >= ?")
            params.append(start_time)
        
        if end_time:
            where_conditions.append("timestamp <= ?")
            params.append(end_time)
        
        # JSON 字段过滤 (SQLite 语法)
        if filter_metadata:
            for key, value in filter_metadata.items():
                # json_extract(properties, '$.key')
                where_conditions.append(f"json_extract(properties, '$.{key}') = ?")
                # 注意：SQLite JSON 提取出的布尔值可能是 0/1，需要适配
                if isinstance(value, bool):
                    params.append(1 if value else 0) # 或者 value 本身，取决于存的时候是 true/false 还是 1/0
                else:
                    params.append(value)
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 安全检查 order_by 防止注入
        allowed_sort_fields = ["timestamp", "created_at", "updated_at"]
        sort_field = order_by.split()[0]
        if sort_field not in allowed_sort_fields:
            order_by = "timestamp DESC"

        cursor.execute(f"""
            SELECT id, user_id, group_id, content, memory_type, timestamp, properties, created_at
            FROM memories
            {where_clause}
            ORDER BY {order_by}
            LIMIT ?
        """, params + [limit])

        memories = []
        for row in cursor.fetchall():
            memory = dict(row)
            if memory.get("properties"):
                memory["properties"] = json.loads(memory["properties"])
            memories.append(memory)
        
        return memories
    
    def update_memory(
        self,
        memory_id: str,
        content: str = None,
        properties: Dict[str, Any] = None
    ) -> bool:
        """更新记忆文档"""
        conn = self.connection
        cursor = conn.cursor()

        updates = []
        params = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)
        
        if properties is not None:
            updates.append("properties = ?")
            params.append(json.dumps(properties))
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")

        params.append(memory_id)

        cursor.execute(f"""
            UPDATE memories
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)

        conn.commit()
        return cursor.rowcount > 0
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆文档"""
        conn = self.connection
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM memories
            WHERE id = ?
        """, (memory_id,))

        conn.commit()
        return cursor.rowcount > 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        conn = self.connection
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS memory_count FROM memories")
        memory_count = cursor.fetchone()["memory_count"]

        cursor.execute("SELECT COUNT(*) AS group_count FROM groups")
        group_count = cursor.fetchone()["group_count"]

        return {
            "memory_count": memory_count,
            "group_count": group_count,
            "store_type": "SQLite",
            "db_path": self.db_path
        }
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self.local, "connection"):
            self.local.connection.close()
            del self.local.connection
            logger.info(f"[OK✅] Closed SQLite connection for {self.db_path}")


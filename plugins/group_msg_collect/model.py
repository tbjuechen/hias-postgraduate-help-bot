import os
import json

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Index, desc, and_, or_, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

# 数据库配置
DATABASE_URL = os.getenv("MESSAGE_DB_URL", "sqlite:///data/messages.db")
Base = declarative_base()

class MessageRecord(Base):
    """消息记录表"""
    __tablename__ = "message_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 基本信息
    message_id = Column(String(64), nullable=False, unique=True, index=True)
    bot_id = Column(String(32), nullable=False)
    platform = Column(String(16), nullable=False, default="onebot-v11")
    
    # 群组和用户信息
    group_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    user_name = Column(String(64))
    user_card = Column(String(64))
    
    # 消息内容
    message_type = Column(String(16), nullable=False)
    raw_message = Column(Text)
    plain_text = Column(Text)
    message_chain = Column(Text)  # JSON字符串
    
    # 时间信息
    created_at = Column(DateTime, nullable=False, index=True)
    recorded_at = Column(DateTime, default=datetime.now)
    
    # 附加信息
    reply_to_message_id = Column(String(64), index=True)
    is_deleted = Column(Boolean, default=False)
    is_recalled = Column(Boolean, default=False)
    
    # 复合索引
    __table_args__ = (
        Index('idx_group_time', 'group_id', 'created_at'),
        Index('idx_user_time', 'user_id', 'created_at'),
        Index('idx_group_user', 'group_id', 'user_id'),
        Index('idx_plain_text', 'plain_text'),  # 用于文本搜索
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'message_id': self.message_id,
            'bot_id': self.bot_id,
            'platform': self.platform,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'user_card': self.user_card,
            'message_type': self.message_type,
            'raw_message': self.raw_message,
            'plain_text': self.plain_text,
            'message_chain': json.loads(self.message_chain) if self.message_chain else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'reply_to_message_id': self.reply_to_message_id,
            'is_deleted': self.is_deleted,
            'is_recalled': self.is_recalled,
        }
    
# 数据库初始化
def init_database():
    """初始化数据库"""
    db_path = Path(DATABASE_URL.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    return engine

engine = init_database()
SessionLocal = sessionmaker(bind=engine)
message_queue = []
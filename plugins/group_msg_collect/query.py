from .model import SessionLocal, MessageRecord

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any



class MessageRecorderAPI:
    """消息记录器查询接口"""
    
    @staticmethod
    def get_session():
        """获取数据库会话"""
        return SessionLocal()
    
    @staticmethod
    def get_messages(
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        message_type: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "desc"  # desc 或 asc
    ) -> List[Dict[str, Any]]:
        """
        查询消息记录
        
        Args:
            group_id: 群组ID
            user_id: 用户ID
            start_time: 开始时间
            end_time: 结束时间
            message_type: 消息类型 (text, image, voice, video, file)
            keyword: 关键词搜索
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序方式 (desc: 新到旧, asc: 旧到新)
        
        Returns:
            消息记录列表
        """
        session = MessageRecorderAPI.get_session()
        try:
            query = session.query(MessageRecord)
            
            # 添加过滤条件
            if group_id:
                query = query.filter(MessageRecord.group_id == group_id)
            if user_id:
                query = query.filter(MessageRecord.user_id == user_id)
            if start_time:
                query = query.filter(MessageRecord.created_at >= start_time)
            if end_time:
                query = query.filter(MessageRecord.created_at <= end_time)
            if message_type:
                query = query.filter(MessageRecord.message_type == message_type)
            if keyword:
                query = query.filter(MessageRecord.plain_text.contains(keyword))
            
            # 排序
            if order_by == "asc":
                query = query.order_by(MessageRecord.created_at.asc())
            else:
                query = query.order_by(MessageRecord.created_at.desc())
            
            # 分页
            query = query.offset(offset).limit(limit)
            
            messages = query.all()
            return [msg.to_dict() for msg in messages]
            
        finally:
            session.close()
    
    @staticmethod
    def get_message_by_id(message_id: str) -> Optional[Dict[str, Any]]:
        """根据消息ID获取消息"""
        session = MessageRecorderAPI.get_session()
        try:
            message = session.query(MessageRecord).filter(
                MessageRecord.message_id == message_id
            ).first()
            return message.to_dict() if message else None
        finally:
            session.close()
    
    @staticmethod
    def get_recent_messages(
        group_id: int, 
        minutes: int = 10, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取最近N分钟的消息"""
        start_time = datetime.now() - timedelta(minutes=minutes)
        return MessageRecorderAPI.get_messages(
            group_id=group_id,
            start_time=start_time,
            limit=limit,
            order_by="asc"
        )
    
    @staticmethod
    def search_messages(
        keyword: str,
        group_id: Optional[int] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """搜索包含关键词的消息"""
        start_time = datetime.now() - timedelta(days=days)
        return MessageRecorderAPI.get_messages(
            group_id=group_id,
            start_time=start_time,
            keyword=keyword,
            limit=limit
        )
    
    @staticmethod
    def get_user_messages(
        user_id: int,
        group_id: Optional[int] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取用户的消息记录"""
        start_time = datetime.now() - timedelta(days=days)
        return MessageRecorderAPI.get_messages(
            group_id=group_id,
            user_id=user_id,
            start_time=start_time,
            limit=limit
        )
    
    @staticmethod
    def get_reply_chain(message_id: str) -> List[MessageRecord]:
        """获取回复链"""
        session = MessageRecorderAPI.get_session()
        try:
            chain = []
            current_id = message_id
            
            # 向上追溯回复链
            while current_id:
                message = session.query(MessageRecord).filter(
                    MessageRecord.message_id == current_id
                ).first()
                
                if not message:
                    break
                    
                chain.insert(0, message)
                current_id = message.reply_to_message_id
            
            # 向下查找被回复的消息
            replies = session.query(MessageRecord).filter(
                MessageRecord.reply_to_message_id == message_id
            ).order_by(MessageRecord.created_at.asc()).all()
            
            for reply in replies:
                chain.append(reply)
            
            return chain
            
        finally:
            session.close()
    
    @staticmethod
    def count_messages(
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        message_type: Optional[str] = None
    ) -> int:
        """统计消息数量"""
        session = MessageRecorderAPI.get_session()
        try:
            query = session.query(MessageRecord)
            
            if group_id:
                query = query.filter(MessageRecord.group_id == group_id)
            if user_id:
                query = query.filter(MessageRecord.user_id == user_id)
            if start_time:
                query = query.filter(MessageRecord.created_at >= start_time)
            if end_time:
                query = query.filter(MessageRecord.created_at <= end_time)
            if message_type:
                query = query.filter(MessageRecord.message_type == message_type)
            
            return query.count()
            
        finally:
            session.close()
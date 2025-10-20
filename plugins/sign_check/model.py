import os
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy import create_engine, Column, String, BigInteger, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. 数据库配置
# 从环境变量读取，或使用默认的 sqlite 文件路径
# 使用不同的数据库文件，避免与消息记录冲突
DATABASE_URL = os.getenv("BINDING_DB_URL", "sqlite:///data/user_bindings.db")

# 2. SQLAlchemy 基类
Base = declarative_base()

class UserBinding(Base):
    """用户绑定信息表"""
    __tablename__ = "user_bindings"
    
    # 主键：QQ号
    # 模仿 MessageRecord 使用 BigInteger 存储 ID
    qq_id = Column(BigInteger, primary_key=True)
    
    # 健：名字
    # nullable=False: 名字不能为空
    # unique=True: 名字必须是唯一的
    name = Column(String(100), nullable=False, unique=True)
    
    # 复合索引 (模仿 MessageRecord 的风格)
    __table_args__ = (
        # 为 'name' 字段创建索引，加快按名称查询
        Index('idx_name', 'name'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'qq_id': self.qq_id,
            'name': self.name,
        }
    
    def __str__(self):
        """字符串表示"""
        return f"UserBinding(QQ: {self.qq_id}, Name: {self.name})"

# 3. 数据库初始化
def init_database():
    """
    初始化数据库：
    1. 确保数据库文件所在的目录存在。
    2. 创建数据库引擎。
    3. 根据 Base 中定义的模型创建所有表。
    """
    # 解析数据库文件路径
    # DATABASE_URL.replace("sqlite:///", "") 用于移除 sqlite 的协议头
    db_path = Path(DATABASE_URL.replace("sqlite:///", ""))
    
    # 确保父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建引擎 (echo=False 关闭 SQL 语句的日志输出)
    engine = create_engine(DATABASE_URL, echo=False)
    
    # 创建所有表
    Base.metadata.create_all(engine)
    
    return engine

# 4. 创建全局引擎和 SessionLocal
# 脚本加载时执行初始化
engine = init_database()
# 创建一个 Session 工厂，插件将使用它来创建会话
SessionLocal = sessionmaker(bind=engine)

def check_binding_conflict(qq_id: int, name_to_bind: str) -> Optional[str]:
    """
    校验绑定冲突 (同步版本)
    
    :return: 冲突原因(str) 或 None(无冲突)
    """
    # 从 Session 工厂创建一个新会话
    session: Session = SessionLocal()
    try:
        # 1. 校验：这个QQ是否被绑定了别的人名
        existing_binding_qq = session.query(UserBinding).filter(
            UserBinding.qq_id == qq_id
        ).one_or_none()
        
        if existing_binding_qq:
            if existing_binding_qq.name == name_to_bind:
                return f"你已经绑定过姓名为 {name_to_bind} 的信息，无需重复绑定。"
            else:
                return f"你的 QQ ({qq_id}) 已经绑定过其他姓名 ({existing_binding_qq.name})。"

        # 2. 校验：这个人名是否已经被使用过
        existing_binding_name = session.query(UserBinding).filter(
            UserBinding.name == name_to_bind
        ).one_or_none()
        
        if existing_binding_name:
            # 名字被别人占用了
            return f"姓名 {name_to_bind} 已经被 QQ ({str(existing_binding_name.qq_id)[:4]}...) 绑定使用。"
            
    finally:
        # 无论如何都要关闭会话
        session.close()
        
    # 3. 没有冲突
    return None

def create_binding(qq_id: int, name_to_bind: str) -> bool:
    """
    创建新的绑定 (同步版本)
    
    :return: True (成功) / False (失败)
    """
    session: Session = SessionLocal()
    try:
        # 创建新对象
        new_binding = UserBinding(qq_id=qq_id, name=name_to_bind)
        # 添加到会话
        session.add(new_binding)
        # 提交事务
        session.commit()
        return True
    except Exception as e:
        # 如果发生错误（例如 unique 约束失败），回滚事务
        session.rollback()
        print(f"创建绑定失败: {e}")
        return False
    finally:
        session.close()
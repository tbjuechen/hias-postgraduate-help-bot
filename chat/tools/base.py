from abc import ABC, abstractmethod
from typing import List, Dict, Union, Optional, Any
from pydantic import BaseModel

class ToolParameters(BaseModel):
    """工具参数基类"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

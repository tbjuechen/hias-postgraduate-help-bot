import os
from typing import Optional, Dict, Any
from pydantic import BaseModel

class Config(BaseModel):
    default_model='deepseek'
    
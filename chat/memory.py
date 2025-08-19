from utils.llm import llm_response

import asyncio

# from plugins.group_msg_collect import on_message_save

class MemoryList(list):
    def __init__(self, callback:callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.size_limit = kwargs.get('size_limit', 20)
        self.callback = callback
        self.pointer = 0
    
    def append(self, object):
        super().append(object)
        if len(self) > self.size_limit and self.pointer != 0:
            self.callback(self.copy())
            self.pointer = len(self)
        
    def clear(self):
        self[:] = self[self.pointer:]
        self.pointer = 0
        
short_term_memory = ''
recent_messages = MemoryList(callback=lambda messages: asyncio.create_task(process_memery(messages)))
def update_short_term_memory(message: str):
    global short_term_memory
    short_term_memory = message
    recent_messages.clear()

def record_knowledge(record: str):
    """
    记录知识到长期记忆
    """
    ...

async def process_memery(message_cache: list):
    """
    使用大模型更新记忆
    """
    joined_recent_messages = '\n'.join(message_cache)
    prompt = '''
你是一个对话记忆压缩助手。

你的任务是根据最近的对话内容，对现有的短期记忆进行更新，总结出对后续对话仍然有用的重要信息。

请注意以下几点：
1. 只保留对话中重要的信息，删除冗余或不必要的内容。
2. 确保更新后的短期记忆简洁明了，便于后续对话使用。
3. 确保短期记忆的时效性，删除过时的信息。
4. 不要输出任何格式化的文本，只需提供纯文本的更新内容。
5. 确保更新后的短期记忆不超过200字。
'''
    question = f'''
现有的短期记忆是：{short_term_memory}
最近的对话内容是：{joined_recent_messages}
'''
    answer = await llm_response(prompt, question)
    update_short_term_memory(answer)

def new_message(message: str):
    """
    处理新的消息
    """
    if not message:
        return
    
    recent_messages.append(message)
    return message
from nonebot import on_command
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_chatrecorder.model import MessageRecord
from utils.rules import allow_group_rule
from datetime import datetime, timedelta, timezone
from openai import AsyncOpenAI
from PIL import Image, ImageDraw, ImageFont
import os
import io
import textwrap
import base64

__plugin_meta__ = PluginMetadata(
    name="省流插件",
    description="基于近期聊天记录生成总结",
    usage="/省流 - 总结近10分钟或近100条消息",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
)

# OpenAI API 配置
BASE_URL = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
API_KEY = os.getenv("OPENAI_API_KEY", None)
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

if not API_KEY:
    raise ValueError("必须设置 OPENAI_API_KEY 来启用省流插件")

openai_client = AsyncOpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

system_prompt = '''
你是一个专业的聊天记录总结助手，需要对QQ群聊天记录进行简洁明了的总结。

总结要求：
1. 提取主要话题和讨论内容
2. 突出重要信息和关键观点
3. 保持客观中性，不添加个人观点
4. 如果有多个话题，分点列出
5. 总结长度控制在200字以内
6. 使用简洁易懂的语言
7. 如果聊天内容过于零散或无意义，可以说明"近期聊天内容较为零散，无明显主题"

输出格式要求：
- 不要使用markdown格式
- 不要使用特殊符号如 # * - 等
- 直接输出纯文本内容
- 可以使用数字编号或简单的换行分段
'''

# 省流命令
summary_cmd = on_command("省流", rule=allow_group_rule, aliases={"总结", "summary"}, priority=5)

async def get_recent_messages(group_id: int, limit_minutes: int = 10, target_count: int = 100):
    """获取近期消息记录，优先按时间，不足则补足100条有效消息"""
    # 计算时间范围 (注意：需要使用UTC时间)
    time_limit = datetime.now(timezone.utc) - timedelta(minutes=limit_minutes)
    
    # 先获取10分钟内的消息
    time_records = await get_message_records(
        scene_ids=[str(group_id)],  # 使用id2s参数指定群组ID
        time_start=time_limit
    )
    
    # 过滤出有效的文本消息
    valid_records = []
    for record in time_records:
        if record.plain_text and record.plain_text.strip():
            valid_records.append(record)
    
    # 如果10分钟内的有效消息已经够100条，直接返回
    if len(valid_records) >= target_count:
        return valid_records[-target_count:]  # 返回最新的100条
    
    # 如果不够，则获取更多历史消息来补足100条
    # 获取更多消息（不限时间，从更早的时间开始）
    earlier_time = datetime.now(timezone.utc) - timedelta(hours=24)  # 获取24小时内的消息
    all_records = await get_message_records(
        scene_ids=[str(group_id)],  # 使用id2s参数指定群组ID
        time_start=earlier_time
    )
    
    # 重新过滤有效消息，只取最近的消息
    all_valid_records = []
    # 按时间倒序排列，获取最新的有效消息
    sorted_records = sorted(all_records, key=lambda x: x.time, reverse=True)
    
    for record in sorted_records:
        if record.plain_text and record.plain_text.strip():
            all_valid_records.append(record)
        if len(all_valid_records) >= target_count:
            break
    
    # 恢复时间顺序并返回
    all_valid_records.reverse()
    return all_valid_records

async def format_messages_for_llm(records: list[MessageRecord], bot: Bot, group_id: int):
    """格式化消息记录供LLM处理"""
    if not records:
        return "无聊天记录"
    
    formatted_messages = []
    
    # 由于已经过滤过，这里直接处理所有记录
    for record in records:
        try:
            # 获取用户昵称
            try:
                member_info = await bot.get_group_member_info(
                    group_id=group_id,
                    user_id=record.user_id,
                    no_cache=True
                )
                username = member_info.get("card") or member_info.get("nickname") or str(record.user_id)
            except:
                username = str(record.user_id)
            
            # 格式化时间
            msg_time = record.time.strftime("%H:%M")
            
            # 使用已有的纯文本消息
            plain_text = record.plain_text.strip()
            
            formatted_messages.append(f"[{msg_time}] {username}: {plain_text}")
                
        except Exception as e:
            continue
    
    return "\n".join(formatted_messages)

async def get_llm_summary(messages: str) -> str:
    """使用LLM生成总结"""
    if messages in ["无聊天记录", "近期无有效文字消息"]:
        return "近期暂无聊天记录或有效消息"
    
    try:
        response = await openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请总结以下QQ群聊天记录：\n\n{messages}"}
            ],
            temperature=0.3,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"生成总结时出错：{str(e)}"

def create_summary_image(summary_text: str, stats_text: str) -> bytes:
    """将总结文本转换为图片"""
    # 图片基本设置
    width = 600
    padding = 40
    line_height = 35
    title_height = 60
    stats_height = 40
    
    # 颜色设置
    bg_color = (255, 255, 255)  # 白色背景
    title_color = (52, 152, 219)  # 蓝色标题
    text_color = (44, 62, 80)  # 深灰色文本
    stats_color = (149, 165, 166)  # 浅灰色统计
    border_color = (189, 195, 199)  # 边框颜色
    
    # 尝试加载字体
    try:
        # Windows
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 24)
        text_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        stats_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    except:
        try:
            # Linux
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            stats_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except:
            # 默认字体
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            stats_font = ImageFont.load_default()
    
    # 文本换行处理
    max_width = width - 2 * padding
    wrapped_lines = []
    
    for line in summary_text.split('\n'):
        if line.strip():
            # 简单的文本换行（基于字符数估算）
            chars_per_line = max_width // 12  # 估算每行字符数
            if len(line) <= chars_per_line:
                wrapped_lines.append(line)
            else:
                # 按标点符号和空格分割
                words = line.replace('，', '，\n').replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
                current_line = ""
                for word in words:
                    if len(current_line + word) <= chars_per_line:
                        current_line += word
                    else:
                        if current_line:
                            wrapped_lines.append(current_line)
                        current_line = word
                if current_line:
                    wrapped_lines.append(current_line)
        else:
            wrapped_lines.append("")
    
    # 计算图片高度
    content_height = len(wrapped_lines) * line_height
    total_height = padding * 2 + title_height + content_height + stats_height + 20
    
    # 创建图片
    img = Image.new('RGB', (width, total_height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 绘制边框
    draw.rectangle([5, 5, width-5, total_height-5], outline=border_color, width=2)
    
    # 绘制标题
    title = "📝 聊天总结"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width - title_width) // 2
    draw.text((title_x, padding), title, fill=title_color, font=title_font)
    
    # 绘制分隔线
    line_y = padding + title_height - 10
    draw.line([padding, line_y, width-padding, line_y], fill=border_color, width=1)
    
    # 绘制总结内容
    y = padding + title_height + 10
    for line in wrapped_lines:
        if line.strip():
            draw.text((padding, y), line, fill=text_color, font=text_font)
        y += line_height
    
    # 绘制统计信息
    stats_y = total_height - stats_height - padding
    draw.text((padding, stats_y), stats_text, fill=stats_color, font=stats_font)
    
    # 转换为字节
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    return img_buffer.getvalue()

@summary_cmd.handle()
async def handle_summary(bot: Bot, event: GroupMessageEvent):
    try:
        group_id = event.group_id
        
        # 发送处理中提示
        await summary_cmd.send("🔄 正在分析近期聊天记录，请稍候...")
        
        # 获取近期消息（已自动过滤图片等无效消息）
        records = await get_recent_messages(group_id)
        
        if not records:
            await summary_cmd.finish("❌ 近期暂无有效聊天记录")
        
        # 格式化消息
        formatted_messages = await format_messages_for_llm(records, bot, group_id)
        
        # 生成总结
        summary = await get_llm_summary(formatted_messages)
        
        # 统计信息
        valid_count = len(records)
        
        # 判断数据来源（是否为10分钟内数据）
        time_limit_local = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent_count = 0
        for record in records:
            # 确保时间比较的时区一致性
            record_time = record.time
            if record_time.tzinfo is None:
                # 如果记录时间没有时区信息，假设为UTC
                record_time = record_time.replace(tzinfo=timezone.utc)
            elif record_time.tzinfo != timezone.utc:
                # 如果有时区但不是UTC，转换为UTC
                record_time = record_time.astimezone(timezone.utc)
            
            if record_time >= time_limit_local:
                recent_count += 1
        
        if recent_count == valid_count and valid_count < 100:
            # 全部都是10分钟内的消息
            stats_text = f"📊 分析了近10分钟内的{valid_count}条有效消息"
        elif recent_count > 0:
            # 混合数据：10分钟内 + 历史补足
            stats_text = f"📊 分析了近10分钟{recent_count}条+历史{valid_count-recent_count}条，共{valid_count}条有效消息"
        else:
            # 纯历史数据
            stats_text = f"📊 近10分钟无消息，分析了最近{valid_count}条有效历史消息"
        
        # 生成图片
        img_bytes = create_summary_image(summary, stats_text)
        
        # 发送图片
        img_base64 = base64.b64encode(img_bytes).decode()
        img_segment = MessageSegment.image(f"base64://{img_base64}")
        
        await summary_cmd.finish(Message(img_segment))
        
    except FinishedException:
        raise  # 正常结束，不处理

    except Exception as e:
        await summary_cmd.finish(f"❌ 生成总结失败：{str(e)}")
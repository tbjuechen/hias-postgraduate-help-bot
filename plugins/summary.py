from nonebot import on_command
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.plugin import PluginMetadata
from utils.rules import allow_group_rule
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import os
import io
import sys
import base64

from utils.llm import llm_response
from plugins.group_msg_collect import MessageRecorderAPI

__plugin_meta__ = PluginMetadata(
    name="省流插件",
    description="基于近期聊天记录生成总结",
    usage="/省流 或 /总结 或 /summary - 总结近10分钟或近100条消息",
    supported_adapters={"~onebot.v11", "~onebot.v12"},
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
summary_cmd = on_command("省流", rule=allow_group_rule, aliases={"总结", "summary"}, priority=5, block=True)

async def get_recent_messages(group_id: int, limit_minutes: int = 10, target_count: int = 100):
    """获取近期消息记录，优先按时间，不足则补足100条有效消息"""
    # 先获取10分钟内的消息
    time_limit = datetime.now() - timedelta(minutes=limit_minutes)
    
    # 获取10分钟内的消息
    recent_messages = MessageRecorderAPI.get_messages(
        group_id=group_id,
        start_time=time_limit,
        limit=200,  # 多获取一些确保有足够的有效消息
        order_by="asc"
    )
    
    # 过滤出有效的文本消息
    valid_recent = []
    for msg in recent_messages:
        if msg.message_type == "text" and msg.plain_text:
            valid_recent.append(msg)
    
    # 如果10分钟内的有效消息已经够100条，直接返回
    if len(valid_recent) >= target_count:
        return valid_recent[-target_count:]  # 返回最新的100条
    
    # 如果不够，则获取更多历史消息来补足100条
    # 获取更多消息（不限时间，从更早的时间开始）
    earlier_time = datetime.now() - timedelta(hours=24)  # 获取24小时内的消息
    all_messages = MessageRecorderAPI.get_messages(
        group_id=group_id,
        start_time=earlier_time,
        limit=300,  # 获取更多消息确保能补足
        order_by="desc"  # 从新到旧
    )
    
    # 过滤有效消息
    all_valid = []
    for msg in all_messages:
        if msg.message_type == "text" and msg.plain_text:
            all_valid.append(msg)
        if len(all_valid) >= target_count:
            break
    
    # 恢复时间顺序并返回
    all_valid.reverse()
    return all_valid

async def format_messages_for_llm(messages: list, bot: Bot, group_id: int):
    """格式化消息记录供LLM处理"""
    if not messages:
        return "无聊天记录"
    
    formatted_messages = [str(msg) for msg in messages]
    
    return "\n".join(formatted_messages)

async def get_llm_summary(messages: str) -> str:
    """使用LLM生成总结"""
    if messages in ["无聊天记录", "近期无有效文字消息"]:
        return "近期暂无聊天记录或有效消息"
    
    try:
        return await llm_response(system_prompt, messages)
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
    
    def load_font(size: int):
        """加载字体，按优先级尝试"""
        
        # Windows 字体
        if sys.platform == "win32":
            windows_fonts = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/arial.ttf"
            ]
            for font_path in windows_fonts:
                try:
                    if os.path.exists(font_path):
                        return ImageFont.truetype(font_path, size)
                except Exception:
                    continue
        
        # Linux/Unix 字体路径
        linux_fonts = [
            # Ubuntu/Debian 中文字体
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 
            "/usr/share/fonts/truetype/arphic/uming.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            
            # CentOS/RHEL 中文字体
            "/usr/share/fonts/chinese/TrueType/uming.ttf",
            "/usr/share/fonts/chinese/TrueType/ukai.ttf",
            "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
            
            # Alpine Linux
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
            
            # Docker容器常见路径
            "/app/fonts/NotoSansSC-Regular.otf",
            "/fonts/simhei.ttf",
            
            # WSL Windows字体
            "/mnt/c/Windows/Fonts/msyh.ttc",
            "/mnt/c/Windows/Fonts/simhei.ttf",
            
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode MS.ttf"
        ]
        
        for font_path in linux_fonts:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                continue
        
        # 尝试系统默认字体
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except:
            try:
                return ImageFont.load_default()
            except:
                return None
    
    # 加载字体
    title_font = load_font(24) or ImageFont.load_default()
    text_font = load_font(18) or ImageFont.load_default()
    stats_font = load_font(14) or ImageFont.load_default()
    
    # 文本换行处理
    max_width = width - 2 * padding
    wrapped_lines = []
    
    for line in summary_text.split('\n'):
        if line.strip():
            # 简单的文本换行（基于字符数估算）
            chars_per_line = max_width // 20  # 估算每行字符数
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
    title = "聊天总结"
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
        messages = await get_recent_messages(group_id)
        
        if not messages:
            await summary_cmd.finish("❌ 近期暂无有效聊天记录")
        
        # 格式化消息
        formatted_messages = await format_messages_for_llm(messages, bot, group_id)
        
        # 生成总结
        summary = await get_llm_summary(formatted_messages)
        
        # 统计信息
        valid_count = len(messages)
        
        # 判断数据来源（是否为10分钟内数据）
        time_limit = datetime.now() - timedelta(minutes=10)
        recent_count = 0
        for msg in messages:
            # 解析消息时间
            created_at = msg.created_at
            if isinstance(created_at, str):
                try:
                    # 处理ISO格式时间字符串
                    msg_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    # 如果有时区信息，转换为本地时间
                    if msg_time.tzinfo:
                        msg_time = msg_time.replace(tzinfo=None)
                    
                    if msg_time >= time_limit:
                        recent_count += 1
                except:
                    continue
        
        if recent_count == valid_count and valid_count < 100:
            # 全部都是10分钟内的消息
            stats_text = f"分析了近10分钟内的{valid_count}条有效消息"
        elif recent_count > 0:
            # 混合数据：10分钟内 + 历史补足
            stats_text = f"分析了近10分钟{recent_count}条+历史{valid_count-recent_count}条，共{valid_count}条有效消息"
        else:
            # 纯历史数据
            stats_text = f"近10分钟无消息，分析了最近{valid_count}条有效历史消息"
        
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
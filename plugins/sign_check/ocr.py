import asyncio
import logging
import os
import sys
import aiohttp
from urllib import parse
from datetime import datetime
from typing import Tuple, TypedDict

API_KEY = os.getenv("OCR_API_KEY")
SECRET_KEY = os.getenv("OCR_SECRET_KEY")

YEAR = 2026
CHECKPOINT = "2025-10-27T22:00:00"

class OCRValidationError(Exception):
    """自定义异常类，用于表示 OCR 校验失败的情况"""
    pass

class QPSLimitError(Exception):
    """自定义异常类，用于表示 OCR API 请求过于频繁的情况"""
    pass

# JSON 类型定义
class Words(TypedDict):
    words: str

class OCRResult(TypedDict):
    words_result: list[Words]
    words_result_num: int
    log_id: str

# 从百度 OCR API 获取识别结果
async def get_ocr_result(image_url) -> OCRResult:
    token = await get_access_token()
    if token is None:
        raise RuntimeError("无法获取 OCR API 的 Access Token")

    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={token}"

    quoted = parse.quote(image_url, safe='')
    payload = f'url={quoted}&detect_direction=false&paragraph=false&probability=false&multidirectional_recognize=false'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=payload.encode("utf-8")) as resp:
            response_json = await resp.json()
            if error_code := response_json.get("error_code"):
                match error_code:
                    case 18:
                        raise QPSLimitError
                    case _:
                        raise RuntimeError(f"OCR API 返回错误，错误码: {error_code}, 信息: {response_json.get('error_msg')}")

            return OCRResult(
                words_result=response_json.get("words_result", []),
                words_result_num=response_json.get("words_result_num", 0),
                log_id=response_json.get("log_id", "")
            )

async def get_access_token() -> str | None:
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            response_json = await resp.json()
            return str(response_json.get("access_token"))

# 从 OCR 结果中提取指定单元格对应的值
def extract(result: OCRResult, key: str) -> str | None:
    for (i, item) in enumerate(result["words_result"]):
        if item["words"].startswith(key):
            if i + 1 < result["words_result_num"]:
                return result["words_result"][i + 1]["words"]
            else:
                break
    return None

def extract_id(result: OCRResult) -> str | None:
    return extract(result, "考生报名号")

# 检查 OCR 结果中的各项内容是否符合预期
def check(result: OCRResult, key: str, *args: str) -> bool:
    value = extract(result, key)
    if value is not None:
        return any(value.startswith(arg) for arg in args)
    return False

def check_school(result: OCRResult) -> bool:
    return check(result, "报考单位", "14430")

def check_major(result: OCRResult) -> bool:
    return check(result, "报考专业", "085404", "085410")

def check_exam(result: OCRResult) -> bool:
    return check(result, "考试方式", "21")

def check_plan(result: OCRResult) -> bool:
    return check(result, "专项计划", "0", "4", "7")

def check_type(result: OCRResult) -> bool:
    return check(result, "报考类别", "11", "12")

def check_department(result: OCRResult) -> bool:
    return check(result, "报考院系所", "216")

def check_topic(result: OCRResult) -> bool:
    return check(result, "研究方向", "01")

def check_duration(result: OCRResult) -> bool:
    return check(result, "学习方式", "全日制")

def check_politics(result: OCRResult) -> bool:
    return check(result, "政治理论", "101")

def check_language(result: OCRResult) -> bool:
    return check(result, "外国语", "204")

def check_math(result: OCRResult) -> bool:
    return check(result, "业务课一", "302")

def check_computer(result: OCRResult) -> bool:
    return check(result, "业务课二", "408")

def check_all(result: OCRResult) -> bool:
    check_list = [
        check_school,
        check_major,
        check_exam,
        check_plan,
        check_type,
        check_department,
        check_topic,
        check_duration,
        check_politics,
        check_language,
        check_math,
        check_computer,
    ]
    return all(f(result) for f in check_list)

# 匹配报名信息标题和打印时间
def match_title(result: OCRResult) -> bool:
    return any(map(lambda x: x["words"].startswith(f"{YEAR}年全国硕士研究生招生考试网上报名信息"),
                   result["words_result"]))

def match_time(result: OCRResult) -> bool:
    for item in result["words_result"]:
        if item["words"].startswith("打印"):
            # 提取时间字符串
            try:
                printed_time = datetime.strptime(item["words"][5:23], "%Y-%m-%d%H：%M：%S")
                logging.debug(printed_time)
                checkpoint = datetime.fromisoformat(CHECKPOINT)
                # 如果打印时间在截止时间之后，认为有效
                delta = printed_time - checkpoint
                return delta.total_seconds() >= 0
            except Exception:
                return False

# OCR 校验主函数
async def ocr_check(image_url: str) -> Tuple[str, str]:
    result = await get_ocr_result(image_url)
    logging.debug(result)

    if result["words_result_num"] == 0:
        raise OCRValidationError("图片中未识别出任何文字")

    if not match_title(result):
        raise OCRValidationError("图片中未检测到有效的报名信息标题")

    if not match_time(result):
        raise OCRValidationError("图片中的打印时间无效，请确保报名表的打印时间在截止时间之后")

    id = extract_id(result)
    if id is None:
        raise OCRValidationError("图片中未检测到有效的考生报名号")

    if not check_all(result):
        raise OCRValidationError("图片识别结果校验未通过，请确保图片清晰且信息完整。")

    return True, id
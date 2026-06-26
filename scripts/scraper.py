"""
通用网页抓取工具
支持 HTTP 请求和 Playwright 浏览器自动化两种模式
"""

import json
import time
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT_DIR / "data" / "raw"

# 请求头，模拟浏览器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 30, encoding: Optional[str] = None) -> str:
    """获取网页 HTML 内容"""
    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        if encoding:
            resp.encoding = encoding
        return resp.text


def fetch_json(url: str, timeout: int = 30) -> dict:
    """获取 JSON API 响应"""
    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def parse_html(html: str) -> BeautifulSoup:
    """解析 HTML"""
    return BeautifulSoup(html, "html.parser")


def save_json(data, filename: str, subdir: str = ""):
    """保存 JSON 数据到 data/raw/"""
    target_dir = DATA_RAW / subdir if subdir else DATA_RAW
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已保存: {filepath} ({len(json.dumps(data, ensure_ascii=False))} 字符)")


def load_json(filename: str, subdir: str = "") -> dict:
    """加载 JSON 数据"""
    target_dir = DATA_RAW / subdir if subdir else DATA_RAW
    filepath = target_dir / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def rate_limit(delay: float = 1.0):
    """请求频率控制"""
    time.sleep(delay)


def safe_fetch(url: str, max_retries: int = 3, delay: float = 2.0) -> Optional[str]:
    """带重试的安全抓取"""
    for attempt in range(max_retries):
        try:
            return fetch_html(url)
        except Exception as e:
            print(f"  ⚠ 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
    print(f"  ✗ 抓取失败: {url}")
    return None


if __name__ == "__main__":
    # 测试
    html = fetch_html("https://www.lib.ustc.edu.cn/")
    soup = parse_html(html)
    title = soup.find("title")
    print(f"测试成功! 页面标题: {title.text if title else 'N/A'}")
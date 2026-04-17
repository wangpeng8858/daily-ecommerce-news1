#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电商资讯早报 - 自动抓取与钉钉推送
"""

import os
import sys
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# ========== 新闻源配置 ==========
# 选择对爬虫友好的、SSR渲染要求低的源
NEWS_SOURCES = [
    {
        "name": "亿邦动力-快讯",
        "url": "https://www.ebrun.com/newest/",
        "selectors": ["div.item h3 a", ".list h3 a", "h3 a"],
        "url_prefix": "https://www.ebrun.com",
        "limit": 5,
    },
    {
        "name": "电商派",
        "url": "https://www.dsb.cn/",
        "selectors": ["a[href*='/p/']", ".content a[href^='/p/']"],
        "url_prefix": "https://www.dsb.cn",
        "limit": 5,
    },
    {
        "name": "钛媒体-电商",
        "url": "https://www.tmtpost.com/tag/28871",
        "selectors": [".title a", ".content_title a", "h3 a", ".index_title a"],
        "url_prefix": "https://www.tmtpost.com",
        "limit": 4,
    },
]

MAX_NEWS_COUNT = 10

# ========== 钉钉配置 ==========
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")


def get_dingtalk_url():
    """生成带签名的钉钉 Webhook URL"""
    url = DINGTALK_WEBHOOK
    if not DINGTALK_SECRET:
        return url

    import hashlib
    import hmac
    import base64
    import urllib.parse

    timestamp = str(int(datetime.now().timestamp() * 1000))
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    hmac_code = hmac.new(
        DINGTALK_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{url}&timestamp={timestamp}&sign={sign}"


def fetch_news_from_source(source):
    """从单个新闻源抓取新闻"""
    news_list = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(source["url"], headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")

        for selector in source["selectors"]:
            elements = soup.select(selector.strip())
            for elem in elements[:source["limit"] * 2]:
                href = elem.get("href", "")
                title = elem.get_text(strip=True)

                # 过滤：标题太短或为空
                if not title or len(title) < 6:
                    continue

                # 处理相对URL
                if href.startswith("/"):
                    href = source["url_prefix"] + href
                elif not href.startswith("http"):
                    continue

                # 过滤：排除导航链接、广告等
                skip_keywords = ["javascript:", "#", "login", "register", "about", "contact"]
                if any(kw in href.lower() for kw in skip_keywords):
                    continue

                news_list.append({"title": title, "url": href})

            if news_list:
                break

        # 去重（同源内）
        seen = set()
        unique = []
        for item in news_list:
            key = item["title"][:15]
            if key not in seen:
                seen.add(key)
                unique.append(item)
        news_list = unique[:source["limit"]]

    except Exception as e:
        print(f"  [ERROR] {source['name']}: {e}")

    return news_list


def fetch_all_news():
    """从所有源抓取新闻并合并去重"""
    all_news = []
    seen_titles = set()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 开始抓取电商资讯...")

    for source in NEWS_SOURCES:
        items = fetch_news_from_source(source)
        for item in items:
            title_key = item["title"][:15].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                item["source"] = source["name"]
                all_news.append(item)
        print(f"  - {source['name']}: {len(items)} 条")

    result = all_news[:MAX_NEWS_COUNT]
    print(f"  合计: {len(result)} 条（已去重）")
    return result


def format_dingtalk_message(news_list):
    """格式化钉钉 Markdown 消息"""
    today = datetime.now().strftime("%Y年%m月%d日")
    now_time = datetime.now().strftime("%H:%M")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_names[datetime.now().weekday()]

    header = f"## 电商资讯早报 | {today} {weekday}"

    if not news_list:
        content = f"{header}\n\n> 今日暂未抓取到资讯，稍后重试\n\n---\n推送时间：{now_time}"
    else:
        items = "\n\n".join(
            f"**{i+1}. {n['title']}**  \n来源：{n['source']} | [查看原文]({n['url']})"
            for i, n in enumerate(news_list)
        )
        content = (
            f"{header}\n\n"
            f"今日精选 **{len(news_list)}** 条电商行业动态\n\n"
            f"---\n\n"
            f"{items}\n\n"
            f"---\n\n"
            f"推送时间：{now_time}  \n"
            f"由 GitHub Actions 自动抓取推送"
        )

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"电商资讯早报 | {today}",
            "text": content,
        },
    }


def send_to_dingtalk(message):
    """发送消息到钉钉群"""
    if not DINGTALK_WEBHOOK:
        print("[WARN] 未配置 DINGTALK_WEBHOOK，跳过发送")
        return False

    try:
        url = get_dingtalk_url()
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(message),
            timeout=10,
        )
        result = resp.json()
        if result.get("errcode") == 0:
            print("[OK] 钉钉消息发送成功!")
            return True
        else:
            print(f"[ERROR] 钉钉返回错误: {result.get('errmsg')} (errcode={result.get('errcode')})")
            return False
    except Exception as e:
        print(f"[ERROR] 钉钉发送异常: {e}")
        return False


def main():
    print("=" * 50)
    print("  电商资讯早报抓取与推送系统")
    print("=" * 50)

    news_list = fetch_all_news()

    if news_list:
        message = format_dingtalk_message(news_list)
        send_to_dingtalk(message)
    else:
        print("\n[WARN] 未抓取到任何资讯，不发送空消息")

    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())

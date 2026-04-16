#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

NEWS_SOURCES = [
    {"name": "亿邦动力", "url": "https://www.ebrun.com/newest/", "selector": ".article-item h3 a, .article-list li a, article h3 a", "limit": 5},
    {"name": "36氪", "url": "https://36kr.com/search/articles/电商", "selector": ".article-item-title a, .kr-news-content a", "limit": 5},
    {"name": "派代网", "url": "https://www.paidai.com", "selector": ".article-title a, h2 a, .post-title a", "limit": 3}
]

MAX_NEWS_COUNT = 8
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")

def get_timestamp():
    return str(int(datetime.now().timestamp() * 1000))

def get_dingtalk_url():
    if not DINGTALK_SECRET:
        return DINGTALK_WEBHOOK
    import hashlib, hmac, base64, urllib.parse
    secret = DINGTALK_SECRET
    timestamp = get_timestamp()
    hmac_code = hmac.new(secret.encode('utf-8'), f'{timestamp}\n{secret}'.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"

def fetch_news_from_source(source):
    news_list = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept-Language': 'zh-CN,zh;q=0.9'}
        response = requests.get(source["url"], headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        selectors = source["selector"].split(",")
        for selector in selectors:
            elements = soup.select(selector.strip())
            for elem in elements[:source["limit"]]:
                href = elem.get("href", "")
                title = elem.get_text(strip=True)
                if href and title and len(title) > 5:
                    if href.startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin("/".join(source["url"].split("/")[:3]), href)
                    news_list.append({"title": title, "url": href})
            if news_list:
                break
    except Exception as e:
        print(f"抓取 {source['name']} 失败: {e}")
    return news_list[:source["limit"]]

def fetch_all_news():
    all_news = []
    seen_titles = set()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 开始抓取电商资讯...")
    for source in NEWS_SOURCES:
        news_list = fetch_news_from_source(source)
        for news in news_list:
            title_key = news["title"][:20].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                news["source"] = source["name"]
                all_news.append(news)
        print(f"  - {source['name']}: 获取 {len(news_list)} 条")
    return all_news[:MAX_NEWS_COUNT]

def format_dingtalk_message(news_list):
    today = datetime.now().strftime("%Y年%m月%d日")
    current_time = datetime.now().strftime("%H:%M")
    if not news_list:
        content = f"## 电商资讯早报 | {today}\n\n今日暂无精选资讯\n\n---\n抓取时间：{current_time}"
    else:
        items = "\n\n".join([f"**{i}. {n['title']}**\n来源：{n['source']} | [查看原文]({n['url']})" for i, n in enumerate(news_list, 1)])
        content = f"## 电商资讯早报 | {today}\n\n今日精选 {len(news_list)} 条电商行业最新动态\n\n---\n\n{items}\n\n---\n抓取时间：{current_time}\n由 AI 自动抓取推送"
    return {"msgtype": "markdown", "markdown": {"title": f"电商资讯早报 | {today}", "text": content}}

def send_to_dingtalk(message):
    if not DINGTALK_WEBHOOK:
        print("未配置钉钉Webhook，跳过发送")
        return True
    try:
        response = requests.post(get_dingtalk_url(), headers={"Content-Type": "application/json"}, data=json.dumps(message), timeout=10)
        result = response.json()
        if result.get("errcode") == 0:
            print("钉钉消息发送成功!")
            return True
        print(f"钉钉消息发送失败: {result.get('errmsg')}")
        return False
    except Exception as e:
        print(f"发送异常: {e}")
        return False

def main():
    print("=" * 50)
    print("电商资讯早报抓取与推送系统")
    print("=" * 50)
    news_list = fetch_all_news()
    print(f"\n共抓取 {len(news_list)} 条资讯")
    if news_list:
        send_to_dingtalk(format_dingtalk_message(news_list))
    return 0

if __name__ == "__main__":
    sys.exit(main())

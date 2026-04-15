#!/usr/bin/env
 python3
# -*- coding: utf-8 -*-
"""
每日电商资讯抓取与推送脚本
支持：钉钉、企业微信、飞书 Webhook
"""

import os
import json
import hmac
import hashlib
import base64
import urllib.parse
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ============ 配置区域 ============

# 资讯源配置
NEWS_SOURCES = [
    {
        "name": "亿邦动力",
        "url": "https:/
/www.ebrun.com/newest/
",
        "selector": ".article-item h3 a",  # 需要根据实际页面调整
        "base_url": "https://www.ebrun.com"
    },
    {
        "name": "36氪",
        "url": "https:/
/36kr.com/search/articles/电商
",
        "selector": ".article-item-title a",
        "base_url": "https://36kr.com"
    }
]

# 推送配置
MAX_NEWS_COUNT = 8  # 每天推送最多8条

# ============ Webhook 工具函数 ============

def get_dingtalk_sign(timestamp, secret):
    """生成钉钉签名"""
    secret_enc = secret.encode('utf-8')
    string_to_sign = f'{timestamp}\n{secret}'
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return sign

def send_dingtalk(webhook, secret, title, content, items):
    """发送钉钉消息"""
    timestamp = str(round(time.time() * 1000))
    
    # 构造签名
    if secret:
        sign = get_dingtalk_sign(timestamp, secret)
        webhook = f"{webhook}&timestamp={timestamp}&sign={sign}"
    
    # 构造 Markdown 消息
    news_list = "\n\n".join([
        f"**{i+1}. {item['title']}**\n"
        f"📰 {item['source']} | 🔗 [查看原文]({item['url']})"
        for i, item in enumerate(items)
    ])
    
    message = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"""## 📰 {title}

{content}

---

{news_list}

---
⏰ 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        }
    }
    
    response = requests.post(webhook, json=message, headers={"Content-Type": "application/json"})
    print(f"钉钉推送结果: {response.status_code} - {response.text}")
    return response.status_code == 200

# ============ 资讯抓取函数 ============

def fetch_news():
    """抓取电商资讯"""
    all_news = []
    
    for source in NEWS_SOURCES:
        try:
            print(f"正在抓取: {source['name']}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
            }
            response = requests.get(source['url'], headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 抓取文章标题和链接
            links = soup.select(source['selector'])[:5]  # 每个源取前5条
            
            for link in links:
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                # 处理相对链接
                if href.startswith('/'):
                    href = source['base_url'] + href
                elif not href.startswith('http'):
                    href = source['base_url'] + '/' + href
                
                if title and href and len(title) > 10:
                    all_news.append({
                        'title': title,
                        'url': href,
                        'source': source['name']
                    })
                    
        except Exception as e:
            print(f"抓取 {source['name']} 失败: {e}")
    
    # 去重并限制数量
    seen = set()
    unique_news = []
    for item in all_news:
        if item['title'] not in seen:
            seen.add(item['title'])
            unique_news.append(item)
    
    return unique_news[:MAX_NEWS_COUNT]

# ============ 主函数 ============

def main():
    print("=" * 50)
    print("开始执行每日电商资讯推送")
    print("=" * 50)
    
    # 获取环境变量
    webhook = os.environ.get('DINGTALK_WEBHOOK')
    secret = os.environ.get('DINGTALK_SECRET')
    
    if not webhook:
        print("错误: 未设置 DINGTALK_WEBHOOK 环境变量")
        return False
    
    # 抓取资讯
    news_items = fetch_news()
    print(f"共抓取到 {len(news_items)} 条资讯")
    
    if not news_items:
        print("没有抓取到资讯，跳过推送")
        return False
    
    # 发送推送
    today = datetime.now().strftime('%m月%d日')
    title = f"电商资讯早报 | {today}"
    content = "今日精选电商行业最新动态，助力经营决策"
    
    success = send_dingtalk(webhook, secret, title, content, news_items)
    
    if success:
        print("✅ 推送成功！")
    else:
        print("❌ 推送失败")
    
    return success

if __name__ == "__main__":
    main()

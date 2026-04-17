#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电商资讯早报 - 智能抓取、去重、分类推送系统
功能：多源抓取 → 关键词分类 → 历史去重 → 格式化推送到钉钉
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ============================================================
# 配置区
# ============================================================

# 新闻抓取源（对爬虫友好，SSR 要求低）
NEWS_SOURCES = [
    {
        "name": "亿邦动力",
        "url": "https://www.ebrun.com/newest/",
        "selectors": ["div.item h3 a", ".list h3 a", "h3 a"],
        "url_prefix": "https://www.ebrun.com",
        "limit": 20,
        "categories": ["规则与政策", "传统电商", "跨境电商", "电商财税"],
    },
    {
        "name": "电商派",
        "url": "https://www.dsb.cn/",
        "selectors": ["a[href*='/p/']"],
        "url_prefix": "https://www.dsb.cn",
        "limit": 20,
        "categories": ["内容电商", "传统电商", "规则与政策"],
    },
    {
        "name": "雨果网",
        "url": "https://www.cifnews.com/news",
        "selectors": ["h3 a", ".news-title a", ".article-title a", ".list-title a", "a.title"],
        "url_prefix": "https://www.cifnews.com",
        "limit": 15,
        "categories": ["跨境电商"],
    },
    {
        "name": "36氪电商",
        "url": "https://36kr.com/information/e-commerce/",
        "selectors": ["a.article-item-title", ".article-item-title a", "h3 a"],
        "url_prefix": "https://36kr.com",
        "limit": 10,
        "categories": ["传统电商", "AI 技术", "规则与政策"],
    },
]

# 分类关键词映射
CATEGORY_KEYWORDS = {
    "规则与政策": [
        "新规", "规范", "监管", "合规", "处罚", "政策", "法规", "条例", "整治",
        "商务部", "工信部", "市场监管", "征求意见", "草案", "暂行", "试行",
        "平台规则", "准入", "禁令", "限制", "打击",
    ],
    "组织架构与人事": [
        "任命", "离职", "辞任", "换届", "人事", "架构调整", "事业部", "合并",
        "拆分", "新高管", "CEO", "总裁", "副总裁", "首席", "总经理", "董事",
        "组织架构", "业务调整", "汇报", "上任", "卸任", "卸任", "调任",
        "淘天", "抖音电商", "京东", "拼多多", "快手", "小红书", "阿里",
    ],
    "淘系平台": [
        "淘宝", "天猫", "淘天", "千牛", "阿里", "1688", "闲鱼", "盒马",
        "速卖通", "Lazada", "阿里妈妈", "淘系", "天猫双11", "天猫618",
    ],
    "内容电商": [
        "抖音", "快手", "小红书", "直播", "短视频", "带货", "达人", "主播",
        "视频号", "B站", "内容", "种草", "笔记", "直播间", "投流",
        "KOL", "KOC", "矩阵", "切片", "切片带货",
    ],
    "传统电商": [
        "京东", "拼多多", "淘宝", "天猫", "苏宁", "唯品会", "当当", "国美",
        "电商", "零售", "商超", "便利店", "O2O", "即时零售",
    ],
    "跨境电商": [
        "跨境", "亚马逊", "Shopee", "Temu", "TikTok Shop", "SHEIN",
        "出海", "海外", "全球化", "独立站", "跨境电商", "外贸",
        "CIFNEWS", "雨果", "Lazada", "速卖通", "海外仓", "FBA",
    ],
    "电商财税": [
        "税务", "财税", "缴税", "税", "发票", "税率", "稽查", "补缴",
        "增值税", "所得税", "关税", "出口退税", "税务总局",
    ],
    "AI 技术": [
        "AI", "人工智能", "大模型", "ChatGPT", "GPT", "文心", "通义",
        "LLM", "智能", "自动化", "算法", "机器学习", "生成式",
        "AIGC", "数字人", "AI客服", "AI电商", "AI工具",
    ],
}

# 平台动态板块 - 需要特别关注的公司
PLATFORM_COMPANIES = ["淘天", "抖音电商", "京东", "拼多多", "快手", "小红书", "阿里", "字节跳动"]

# 钉钉配置
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")

# 历史记忆文件路径（仓库内）
MEMORY_FILE = "data/pushed_topics.md"


# ============================================================
# 历史去重模块
# ============================================================

def load_pushed_tags_from_local():
    """从本地 data/pushed_topics.md 读取已推送标签"""
    pushed = set()
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    if not os.path.exists(filepath):
        return pushed

    today = datetime.now()
    in_recent = False
    current_tags = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                try:
                    date_str = line.replace("## ", "").strip()
                    push_date = datetime.strptime(date_str, "%Y-%m-%d")
                    in_recent = (today - push_date).days <= 7
                except ValueError:
                    in_recent = False
                continue
            if in_recent and line.startswith("- tags:"):
                tags_str = line.replace("- tags:", "").strip().strip("[]")
                tags = [t.strip().strip("'\"") for t in tags_str.split(",")]
                pushed.update(t.lower() for t in tags if t.strip())

    return pushed


def load_memory_content_local():
    """读取完整的 memory 文件内容"""
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_memory_local(memory_content):
    """保存 memory 到本地文件（checkout 目录中）"""
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(memory_content)


def git_commit_and_push():
    """通过 git 命令提交并推送 memory 文件变更"""
    import subprocess
    try:
        # Actions 环境中自带 git，且已配置好 token
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run(["git", "-C", repo_dir, "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "add", MEMORY_FILE], check=True, capture_output=True)
        result = subprocess.run(["git", "-C", repo_dir, "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            print("[INFO] memory 文件无变更，跳过提交")
            return
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", f"docs: update pushed topics {datetime.now().strftime('%Y-%m-%d')}"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "push"], check=True, capture_output=True)
        print("[OK] 历史记忆已提交并推送到仓库")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] git 操作失败: {e}")
        if e.stderr:
            print(f"  stderr: {e.stderr.decode('utf-8', errors='replace')[:200]}")


# ============================================================
# 新闻抓取模块
# ============================================================

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

                if not title or len(title) < 6:
                    continue

                if href.startswith("/"):
                    href = source["url_prefix"] + href
                elif not href.startswith("http"):
                    continue

                skip_kw = ["javascript:", "#", "login", "register", "about", "contact"]
                if any(kw in href.lower() for kw in skip_kw):
                    continue

                news_list.append({
                    "title": title,
                    "url": href,
                    "source": source["name"],
                    "categories": source.get("categories", []),
                })

            if news_list:
                break

        # 同源去重
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
    """从所有源抓取新闻"""
    all_news = []
    seen_titles = set()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 开始抓取电商资讯...")

    for source in NEWS_SOURCES:
        items = fetch_news_from_source(source)
        for item in items:
            title_key = item["title"][:15].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_news.append(item)
        print(f"  - {source['name']}: {len(items)} 条")

    print(f"  原始合计: {len(all_news)} 条")
    return all_news


# ============================================================
# 分类与标签模块
# ============================================================

def classify_and_tag(item):
    """
    对每条资讯进行分类和打标签
    返回: (categories_list, tags_list, is_platform_dynamic)
    """
    title = item["title"].lower()
    matched_categories = []

    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in title:
                if cat not in matched_categories:
                    matched_categories.append(cat)
                break

    # 如果没有匹配到任何分类，根据来源给一个默认分类
    if not matched_categories:
        matched_categories = item.get("categories", ["行业动态"])

    # 生成标签：从标题中提取关键名词短语
    tags = extract_tags(item["title"])

    # 判断是否是平台动态
    is_platform = False
    if "组织架构与人事" in matched_categories:
        is_platform = True
    for company in PLATFORM_COMPANIES:
        if company.lower() in title:
            is_platform = True
            break

    return matched_categories, tags, is_platform


def extract_tags(title):
    """从标题中提取核心关键词作为标签"""
    # 移除常见虚词
    stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
                  "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
                  "会", "着", "没有", "看", "好", "自己", "这", "被", "她", "他",
                  "它", "与", "及", "等", "将", "已", "对", "为", "从", "可",
                  "让", "把", "被", "比", "更", "最", "其", "如何", "如何", "什么"}
    words = re.findall(r'[\u4e00-\u9fa5]{2,}|[A-Za-z]+(?:\s[A-Za-z]+)*', title)
    tags = []
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w not in stop_words:
            tags.append(w)

    # 去重并取前6个
    seen = set()
    unique_tags = []
    for t in tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            unique_tags.append(t)
        if len(unique_tags) >= 6:
            break

    return unique_tags if unique_tags else [title[:10]]


def check_duplicate(tags, pushed_tags):
    """
    检查是否与近7天已推送的内容高度重复
    规则：核心关键词3个以上匹配则跳过
    """
    if not pushed_tags:
        return False
    match_count = sum(1 for t in tags if t.lower() in pushed_tags)
    return match_count >= 3


def format_memory_entry(news_list):
    """生成今日推送记录的 Markdown 条目"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"## {today}", ""]
    for item in news_list:
        tags_str = ", ".join(f"'{t}'" for t in item.get("tags", []))
        cats_str = ", ".join(item.get("categories", []))
        lines.append(f"- {item['title']}")
        lines.append(f"  - tags: [{tags_str}]")
        lines.append(f"  - cats: [{cats_str}]")
        lines.append(f"  - url: {item['url']}")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 消息格式化模块
# ============================================================

def build_description(item):
    """根据标题和分类生成简要描述"""
    title = item["title"]
    cats = item.get("categories", [])

    # 根据标题中是否包含具体数字或关键事件信息来判断
    if any(w in title for w in ["发布", "宣布", "推出", "上线", "发布", "更新", "调整", "升级"]):
        return "相关动态更新，详情请查看原文。"
    return "行业最新动态，详情请查看原文。"


def is_taobao_related(item):
    """判断是否是淘系相关内容（需详细展开）"""
    cats = item.get("categories", [])
    tags = item.get("tags", [])
    taobao_markers = ["淘宝", "天猫", "淘天", "阿里", "千牛", "1688", "闲鱼", "盒马", "阿里妈妈"]
    if "淘系平台" in cats:
        return True
    for t in tags:
        if any(m in t for m in taobao_markers):
            return True
    return False


def format_dingtalk_message(news_list):
    """格式化钉钉 Markdown 消息"""
    today = datetime.now().strftime("%Y年%m月%d日")
    now_time = datetime.now().strftime("%H:%M")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_names[datetime.now().weekday()]

    # 分离普通资讯和平台动态
    platform_items = []
    regular_items = []
    for item in news_list:
        if item.get("is_platform", False):
            platform_items.append(item)
        else:
            regular_items.append(item)

    # 构建消息
    header = f"## 📰 电商资讯早报 | {today} {weekday}"

    # 平台动态板块
    platform_section = ""
    if platform_items:
        platform_section = "\n\n### 🏢 平台动态\n\n"
        for i, item in enumerate(platform_items, 1):
            desc = build_description(item)
            cats = "、".join(item.get("categories", []))
            platform_section += (
                f"**{i}. {item['title']}**\n\n"
                f"类别：{cats}\n"
                f"{desc}\n\n"
                f"📎 [查看原文]({item['url']})\n\n"
            )
        platform_section += "---\n"

    # 普通资讯板块
    news_section = ""
    if regular_items:
        news_section = "\n\n### 📋 今日资讯\n\n"
        for i, item in enumerate(regular_items, 1):
            desc = build_description(item)
            is_tb = is_taobao_related(item)
            cats = "、".join(item.get("categories", []))
            source = item.get("source", "")

            if is_tb:
                # 淘系内容详细展开
                news_section += (
                    f"**{i}. {item['title']}**  \n"
                    f"来源：{source} | 类别：{cats}\n\n"
                    f"📝 **核心要点：**\n"
                    f"- 此为淘系平台相关重要动态\n"
                    f"- 建议及时关注并评估对店铺运营的影响\n\n"
                    f"📎 [查看原文]({item['url']})\n\n"
                )
            else:
                # 其他内容简写
                news_section += (
                    f"**{i}. {item['title']}**  \n"
                    f"来源：{source} | {desc}  \n"
                    f"📎 [查看原文]({item['url']})\n\n"
                )
        news_section += "---\n"

    # 关键词总结
    all_tags = []
    for item in news_list:
        all_tags.extend(item.get("tags", []))
    # 统计高频标签
    tag_count = {}
    for t in all_tags:
        tl = t.lower()
        tag_count[tl] = tag_count.get(tl, 0) + 1
    top_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:10]
    keyword_section = "\n\n### 🔑 今日关键词\n\n"
    keyword_section += "、".join([f"`{tag}`" for tag, _ in top_tags])

    # 组合
    if not news_list:
        content = f"{header}\n\n> 今日暂未检索到电商资讯\n\n---\n推送时间：{now_time}"
    else:
        content = (
            f"{header}\n\n"
            f"今日精选 **{len(news_list)}** 条电商行业动态\n"
            f"---"
            f"{platform_section}"
            f"{news_section}"
            f"{keyword_section}\n\n"
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


# ============================================================
# 钉钉发送模块
# ============================================================

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
            data=json.dumps(message, ensure_ascii=False),
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


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  电商资讯早报 - 智能抓取·去重·分类推送系统")
    print("=" * 60)

    # Step 0: 读取历史记忆
    print("\n[Step 0] 读取历史推送记录...")
    memory_content = load_memory_content_local()
    if memory_content:
        print("  已加载本地历史记忆文件")
    else:
        print("  无历史记忆文件，首次运行")

    pushed_tags = load_pushed_tags_from_local()
    print(f"  近7天已推送标签: {len(pushed_tags)} 个")

    # Step 1: 抓取今日资讯
    print("\n[Step 1] 检索今日电商资讯...")
    raw_news = fetch_all_news()

    # Step 2: 分类、标签、去重
    print("\n[Step 2] 分类、标签、去重...")
    final_news = []
    for item in raw_news:
        categories, tags, is_platform = classify_and_tag(item)
        item["categories"] = categories
        item["tags"] = tags
        item["is_platform"] = is_platform

        # 去重检查
        if check_duplicate(tags, pushed_tags):
            print(f"  [SKIP] 重复: {item['title'][:30]}...")
            continue

        final_news.append(item)

    print(f"  最终待推送: {len(final_news)} 条（去重后）")

    # Step 3: 格式化并发送
    if final_news:
        print("\n[Step 3] 格式化并发送到钉钉...")
        message = format_dingtalk_message(final_news)
        send_to_dingtalk(message)

        # Step 4: 保存历史记忆
        print("\n[Step 4] 更新历史推送记录...")
        new_entry = format_memory_entry(final_news)
        if memory_content:
            updated_memory = new_entry + "\n---\n\n" + memory_content
        else:
            updated_memory = "# 电商资讯推送历史记录\n\n" + new_entry + "\n"
        save_memory_local(updated_memory)
        git_commit_and_push()
    else:
        print("\n[INFO] 今日无新资讯可推送（全部重复或无内容）")

    print("\n" + "=" * 60)
    print("  执行完毕")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

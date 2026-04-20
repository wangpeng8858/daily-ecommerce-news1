#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电商资讯早报 v2.0 - 精准分类·分层推送
核心逻辑：
  1. 多源抓取 → 2. 关键词智能分类 → 3. 7天去重
  4. 分层排版：淘系/AI重点展开 + 其他平台观点摘要
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ============================================================
# 新闻源配置
# ============================================================

NEWS_SOURCES = [
    {
        "name": "亿邦动力",
        "url": "https://www.ebrun.com/newest/",
        "selectors": ["h3 a", "div.item h3 a", ".list h3 a"],
        "url_prefix": "https://www.ebrun.com",
        "limit": 30,
    },
    {
        "name": "电商派",
        "url": "https://www.dsb.cn/",
        "selectors": ["a[href*='/p/']"],
        "url_prefix": "https://www.dsb.cn",
        "limit": 30,
    },
    {
        "name": "DoNews",
        "url": "https://www.donews.com/",
        "selectors": [".title a", "h3 a", ".article-title a"],
        "url_prefix": "https://www.donews.com",
        "limit": 20,
    },
    {
        "name": "钛媒体",
        "url": "https://www.tmtpost.com/nictation/",
        "selectors": ["h3 a", ".content-item a"],
        "url_prefix": "https://www.tmtpost.com",
        "limit": 15,
    },
]

# ============================================================
# 智能分类系统
# ============================================================

# 平台标识关键词（决定归属哪个平台板块）
PLATFORM_KEYWORDS = {
    "淘系": {
        "primary": ["淘宝", "天猫", "淘天", "千牛", "阿里妈妈", "闲鱼", "盒马", "1688", "速卖通", "Lazada", "菜鸟", "阿里云", "淘宝直播", "天猫国际", "阿里"],
        "ai": ["通义", "Qwen", "夸克", "阿里AI", "淘宝AI", "天猫AI", "阿里大模型"],
    },
    "抖音": {
        "primary": ["抖音", "抖音电商", "字节跳动", "字节", "TikTok", "今日头条", "西瓜视频", "红果", "红果短剧"],
        "ai": ["豆包", "云雀", "抖音AI", "字节AI", "TikTok AI"],
    },
    "京东": {
        "primary": ["京东", "JD", "京喜", "京东物流", "京东科技", "达达"],
        "ai": ["言犀", "京东AI", "ChatJD"],
    },
    "拼多多": {
        "primary": ["拼多多", "PDD", "Temu", "多多", "拼团"],
        "ai": [],
    },
    "快手": {
        "primary": ["快手", "快手电商", "快手科技", "磁力引擎"],
        "ai": ["快意", "快手AI"],
    },
    "小红书": {
        "primary": ["小红书", "RED", "REDnote"],
        "ai": [],
    },
}

# 非平台的专题关键词
TOPIC_KEYWORDS = {
    "AI 技术": ["AI", "人工智能", "大模型", "ChatGPT", "GPT", "LLM", "AIGC", "生成式", "数字人", "AI客服", "AI工具", "AI电商", "智能体", "Agent", "Sora", "Midjourney", "Claude", "Gemini", "文心", "智谱", "深度学习", "机器学习"],
    "跨境电商": ["跨境", "亚马逊", "Shopee", "出海", "海外", "独立站", "跨境电商", "外贸", "SHEIN", "TikTok Shop", "海外仓", "FBA", "DTC"],
    "电商财税": ["税务", "财税", "缴税", "发票", "税率", "稽查", "补缴", "增值税", "所得税", "关税", "出口退税", "税务总局", "偷税", "逃税", "税务筹划"],
    "规则与政策": ["新规", "监管", "合规", "处罚", "政策", "法规", "条例", "整治", "商务部", "工信部", "市场监管", "征求意见", "平台规则", "准入", "禁令", "反垄断", "不正当竞争", "数据安全", "隐私保护"],
    "组织人事": ["任命", "离职", "辞任", "换届", "人事变动", "架构调整", "事业部", "新高管", "CEO", "总裁", "副总裁", "首席", "总经理", "董事", "上任", "卸任", "调任", "裁员", "优化"],
    "消费零售": ["零售", "商超", "便利店", "O2O", "即时零售", "生鲜", "即时配送", "消费", "新消费", "品牌", "供应链", "门店"],
}

# ============================================================
# 配置
# ============================================================

DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")
MEMORY_FILE = "data/pushed_topics.md"


# ============================================================
# 历史去重
# ============================================================

def load_pushed_tags():
    """从本地 data/pushed_topics.md 读取近7天已推送标签"""
    pushed = set()
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    if not os.path.exists(filepath):
        return pushed

    today = datetime.now()
    in_recent = False
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


def load_memory_content():
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_memory(content):
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), MEMORY_FILE)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def git_commit_and_push():
    import subprocess
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run(["git", "-C", repo_dir, "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "add", MEMORY_FILE], check=True, capture_output=True)
        result = subprocess.run(["git", "-C", repo_dir, "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            return
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", f"docs: update pushed topics {datetime.now().strftime('%Y-%m-%d')}"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "push"], check=True, capture_output=True)
        print("[OK] 历史记忆已同步")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] git同步失败: {e}")


# ============================================================
# 新闻抓取
# ============================================================

def fetch_source(source):
    items = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = requests.get(source["url"], headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in source["selectors"]:
            elems = soup.select(sel.strip())
            for elem in elems[:source["limit"] * 2]:
                href = elem.get("href", "")
                title = elem.get_text(strip=True)
                if not title or len(title) < 8:
                    continue
                if href.startswith("/"):
                    href = source["url_prefix"] + href
                elif not href.startswith("http"):
                    continue
                skip = ["javascript:", "#", "login", "register", "about", "contact", "void"]
                if any(k in href.lower() for k in skip):
                    continue
                items.append({"title": title, "url": href, "source": source["name"]})
            if items:
                break

        # 同源去重
        seen = set()
        unique = []
        for item in items:
            key = item["title"][:12]
            if key not in seen:
                seen.add(key)
                unique.append(item)
        items = unique[:source["limit"]]

    except Exception as e:
        print(f"  [ERR] {source['name']}: {e}")
    return items


def fetch_all():
    all_news = []
    seen = set()
    print(f"[{datetime.now().strftime('%H:%M')}] 抓取资讯...")
    for src in NEWS_SOURCES:
        items = fetch_source(src)
        for item in items:
            key = item["title"][:12].lower()
            if key not in seen:
                seen.add(key)
                all_news.append(item)
        print(f"  {src['name']}: {len(items)} 条")
    print(f"  合计: {len(all_news)} 条")
    return all_news


# ============================================================
# 智能分类引擎
# ============================================================

def classify_item(title):
    """
    对标题进行分类，返回:
    - platform: 所属平台（淘系/抖音/京东/... 或 None）
    - is_ai: 是否AI相关
    - topics: 匹配的专题列表
    - priority: 优先级 (1=淘系+AI, 2=淘系, 3=其他AI, 4=其他)
    """
    t = title.lower()
    platform = None
    is_ai = False

    # 检查平台归属
    for plat, kws in PLATFORM_KEYWORDS.items():
        for kw in kws["primary"]:
            if kw.lower() in t:
                platform = plat
                break
        if platform:
            # 检查该平台AI关键词
            for ai_kw in kws.get("ai", []):
                if ai_kw.lower() in t:
                    is_ai = True
                    break
            break

    # 检查通用AI关键词（即使没匹配到具体平台）
    if not is_ai:
        for kw in TOPIC_KEYWORDS.get("AI 技术", []):
            if kw.lower() in t:
                is_ai = True
                break

    # 匹配专题
    topics = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if topic == "AI 技术":
            continue
        for kw in kws:
            if kw.lower() in t:
                if topic not in topics:
                    topics.append(topic)
                break

    # 优先级
    if platform == "淘系" and is_ai:
        priority = 1
    elif platform == "淘系":
        priority = 2
    elif is_ai:
        priority = 3
    else:
        priority = 4

    return platform, is_ai, topics, priority


def extract_tags(title):
    """提取关键词标签"""
    stop = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
            "一", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
            "没", "看", "好", "这", "被", "它", "与", "及", "等", "将", "已",
            "对", "为", "从", "可", "让", "把", "更", "最", "其", "什么"}
    words = re.findall(r'[\u4e00-\u9fa5]{2,}|[A-Za-z]+(?:\s[A-Za-z]+)*', title)
    tags = []
    seen = set()
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w not in stop and w.lower() not in seen:
            seen.add(w.lower())
            tags.append(w)
        if len(tags) >= 6:
            break
    return tags if tags else [title[:10]]


def is_duplicate(tags, pushed_tags):
    if not pushed_tags:
        return False
    return sum(1 for t in tags if t.lower() in pushed_tags) >= 3


# ============================================================
# 消息格式化 v2.0 - 分层排版
# ============================================================

def format_message(news_list):
    """
    分层排版策略：
    ━ 第一层：淘系平台（含AI）→ 重点展开
    ━ 第二层：AI电商技术（非淘系）→ 重点展开
    ━ 第三层：其他平台动态 → 观点 + 链接
    ━ 第四层：行业专题（政策/财税/跨境/消费/人事）→ 观点 + 链接
    """
    today = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
    now_time = datetime.now().strftime("%H:%M")

    # 按层级分组
    layers = {
        "taobao": [],     # 淘系（含AI）
        "ai": [],         # AI电商（非淘系）
        "platform": {},   # 其他平台
        "topic": {},      # 专题
    }

    platform_order = ["抖音", "京东", "拼多多", "快手", "小红书"]

    for item in news_list:
        platform, is_ai, topics, priority = item["meta"]
        if priority in (1, 2):
            layers["taobao"].append(item)
        elif priority == 3:
            layers["ai"].append(item)
        elif platform:
            if platform not in layers["platform"]:
                layers["platform"][platform] = []
            layers["platform"][platform].append(item)
        else:
            for tp in topics:
                if tp not in layers["topic"]:
                    layers["topic"][tp] = []
                layers["topic"][tp].append(item)
            if not topics:
                if "行业动态" not in layers["topic"]:
                    layers["topic"]["行业动态"] = []
                layers["topic"]["行业动态"].append(item)

    # 构建消息
    parts = []
    parts.append(f"## 📰 电商资讯早报 | {today} {weekday}")
    parts.append(f"\n> 今日精选 **{len(news_list)}** 条行业动态  |  更新时间 {now_time}")
    parts.append("---")

    # 第一层：淘系（重点展开）
    if layers["taobao"]:
        parts.append("\n### 🔴 淘系焦点")
        parts.append("")
        for i, item in enumerate(layers["taobao"], 1):
            platform, is_ai, topics, priority = item["meta"]
            ai_tag = " 🤖" if is_ai else ""
            source = item["source"]
            parts.append(f"**{i}. {item['title']}**{ai_tag}")
            parts.append(f"")
            # 生成简要点评
            topics_str = "、".join(topics) if topics else "平台动态"
            parts.append(f"🏷️ `{topics_str}`  |  📌 来源：{source}")
            parts.append(f"")
            parts.append(f"📎 [查看原文]({item['url']})")
            parts.append("")

    # 第二层：AI电商（重点展开）
    if layers["ai"]:
        parts.append("\n### 🤖 AI + 电商")
        parts.append("")
        for i, item in enumerate(layers["ai"], 1):
            source = item["source"]
            platform = item["meta"][0]
            plat_tag = f" · {platform}" if platform else ""
            parts.append(f"**{i}. {item['title']}**")
            parts.append(f"")
            topics = item["meta"][2]
            topics_str = "、".join(topics) if topics else "AI动态"
            parts.append(f"🏷️ `{topics_str}`{plat_tag}  |  📌 来源：{source}")
            parts.append(f"")
            parts.append(f"📎 [查看原文]({item['url']})")
            parts.append("")

    # 第三层：其他平台
    for plat in platform_order:
        items = layers["platform"].get(plat, [])
        if not items:
            continue
        parts.append(f"\n### 📢 {plat}")
        parts.append("")
        for item in items[:5]:  # 每个平台最多5条
            source = item["source"]
            parts.append(f"- [{item['title']}]({item['url']})  _{source}_")
        parts.append("")

    # 第四层：行业专题
    topic_order = ["规则与政策", "组织人事", "消费零售", "跨境电商", "电商财税", "行业动态"]
    for tp in topic_order:
        items = layers["topic"].get(tp, [])
        if not items:
            continue
        parts.append(f"\n### 📋 {tp}")
        parts.append("")
        for item in items[:5]:
            source = item["source"]
            parts.append(f"- [{item['title']}]({item['url']})  _{source}_")
        parts.append("")

    # 关键词云
    all_tags = []
    for item in news_list:
        all_tags.extend(item.get("tags", []))
    tag_count = {}
    for t in all_tags:
        tl = t.lower()
        tag_count[tl] = tag_count.get(tl, 0) + 1
    top_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:12]
    if top_tags:
        parts.append("\n### 🔑 关键词")
        parts.append("")
        parts.append("  ".join([f"`{tag}`" for tag, _ in top_tags]))

    # 结尾
    parts.append("\n---")
    parts.append(f"推送时间：{now_time}  |  GitHub Actions 自动抓取")
    parts.append(f"数据来源：亿邦动力 · 电商派 · DoNews · 钛媒体")

    content = "\n".join(parts)

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"电商资讯 | {today}",
            "text": content,
        },
    }


# ============================================================
# 钉钉发送
# ============================================================

def get_dingtalk_url():
    url = DINGTALK_WEBHOOK
    if not DINGTALK_SECRET:
        return url
    import hashlib, hmac, base64, urllib.parse
    timestamp = str(int(datetime.now().timestamp() * 1000))
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    hmac_code = hmac.new(
        DINGTALK_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{url}&timestamp={timestamp}&sign={sign}"


def send_dingtalk(message):
    if not DINGTALK_WEBHOOK:
        print("[WARN] 未配置 DINGTALK_WEBHOOK")
        return False
    try:
        url = get_dingtalk_url()
        resp = requests.post(url, headers={"Content-Type": "application/json"},
                           data=json.dumps(message, ensure_ascii=False), timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print("[OK] 钉钉推送成功!")
            return True
        else:
            print(f"[ERR] 钉钉错误: {result.get('errmsg')}")
            return False
    except Exception as e:
        print(f"[ERR] 钉钉异常: {e}")
        return False


# ============================================================
# 记忆条目格式化
# ============================================================

def format_memory_entry(news_list):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"## {today}", ""]
    for item in news_list:
        tags_str = ", ".join(f"'{t}'" for t in item.get("tags", []))
        cats_str = ", ".join(item["meta"][2]) if item["meta"][2] else "general"
        plat = item["meta"][0] or "none"
        lines.append(f"- {item['title']}")
        lines.append(f"  - tags: [{tags_str}]")
        lines.append(f"  - platform: {plat}")
        lines.append(f"  - topics: [{cats_str}]")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 50)
    print("  电商资讯早报 v2.0 - 精准分类·分层推送")
    print("=" * 50)

    # Step 0: 加载历史
    print("\n[0] 加载历史记录...")
    pushed_tags = load_pushed_tags()
    memory_content = load_memory_content()
    print(f"  已有标签: {len(pushed_tags)} 个")

    # Step 1: 抓取
    print("\n[1] 抓取资讯...")
    raw = fetch_all()

    # Step 2: 分类 + 去重
    print("\n[2] 智能分类与去重...")
    final = []
    for item in raw:
        platform, is_ai, topics, priority = classify_item(item["title"])
        item["meta"] = (platform, is_ai, topics, priority)
        item["tags"] = extract_tags(item["title"])

        if is_duplicate(item["tags"], pushed_tags):
            print(f"  [SKIP] {item['title'][:25]}...")
            continue
        final.append(item)

    # 统计
    taobao_count = sum(1 for i in final if i["meta"][0] == "淘系")
    ai_count = sum(1 for i in final if i["meta"][1])
    other_plat = set(i["meta"][0] for i in final if i["meta"][0] and i["meta"][0] != "淘系")
    print(f"  最终: {len(final)} 条（淘系 {taobao_count} | AI相关 {ai_count} | 其他平台 {len(other_plat)}个）")

    # Step 3: 发送
    if final:
        print("\n[3] 格式化推送...")
        msg = format_message(final)
        send_dingtalk(msg)

        # Step 4: 保存记忆
        print("\n[4] 更新历史...")
        entry = format_memory_entry(final)
        if memory_content:
            updated = entry + "\n---\n\n" + memory_content
        else:
            updated = "# 电商资讯推送历史\n\n" + entry + "\n"
        save_memory(updated)
        git_commit_and_push()
    else:
        print("\n[INFO] 无新资讯")

    print("\n" + "=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())

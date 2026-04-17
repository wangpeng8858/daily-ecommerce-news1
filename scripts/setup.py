#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup.py - 初始化仓库配置（在 Actions 中运行）
首次运行时更新 workflow 文件并创建 data 目录
"""
import os
import json
import base64
import urllib.request

REPO = "wangpeng8858/daily-ecommerce-news1"

def api_get(path):
    token = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{REPO}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "Python")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def api_put(path, data):
    token = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{REPO}/{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "Python")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def main():
    print("[Setup] 检查 data/pushed_topics.md 是否存在...")
    try:
        info = api_get("contents/data/pushed_topics.md")
        print(f"  已存在 (SHA: {info['sha'][:8]}...)")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 创建空的记忆文件
            print("  不存在，创建中...")
            content = base64.b64encode(b"# 电商资讯推送历史记录\n\n").decode()
            api_put("contents/data/pushed_topics.md", {
                "message": "init: create pushed topics memory file",
                "content": content,
            })
            print("  已创建 data/pushed_topics.md")
        else:
            raise

    print("[Setup] 完成!")

if __name__ == "__main__":
    main()

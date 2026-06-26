import httpx
import json

# 获取所有标签
tags_data = httpx.get('https://ustcforum.com/api/tags').json()
tag_ids = {t['id']: t['attributes']['name'] for t in tags_data['data']}

print("标签 ID 对照表:")
for tid, name in sorted(tag_ids.items()):
    print(f"  {tid}: {name}")

print("\n" + "="*50 + "\n")

# 查看帖子可以打多个标签还是只能打一个
data = httpx.get('https://ustcforum.com/api/discussions?filter[tag]=help&page[limit]=10').json()
posts = data.get('data', [])

print(f"帖子数: {len(posts)}\n")
for p in posts[:10]:
    title = p['attributes']['title']
    tags = p.get('relationships', {}).get('tags', {}).get('data', [])
    tag_names = [tag_ids.get(t['id'], '未知') for t in tags]
    print(f"标题: {title}")
    print(f"标签: {tag_names}")
    print("---")
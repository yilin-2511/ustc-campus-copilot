import json

# 查看现有 Q&A 数据
with open('data/raw/n7teahouse/n7_qa_knowledge.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

entries = data.get('entries', [])
print(f'条目数: {len(entries)}')
print('='*60)

for i, e in enumerate(entries, 1):
    print(f'\n{i}. {e.get("question", "")}')
    print(f'   分类: {e.get("category", "")}')
    print(f'   答案: {e.get("answer", "")[:100]}...')
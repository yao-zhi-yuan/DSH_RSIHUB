import json

def summarize_jsonl(text):
    rows = [json.loads(line) for line in text.splitlines()]
    return {'valid': len(rows), 'invalid': 0, 'total_value': sum(row['value'] for row in rows)}

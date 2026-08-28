import hashlib, json

def canonical_key(value):
    return hashlib.md5(json.dumps(value).encode()).hexdigest()

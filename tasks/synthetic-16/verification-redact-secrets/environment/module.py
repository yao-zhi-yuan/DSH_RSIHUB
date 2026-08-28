import re

def redact(text):
    return re.sub(r'token=\w+', 'token=[REDACTED]', text)

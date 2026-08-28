from pathlib import Path

def safe_relative_path(value):
    return str(Path(value))

def clamp(value, lower, upper):
    if value < lower:
        return upper
    if value > upper:
        return lower
    return value

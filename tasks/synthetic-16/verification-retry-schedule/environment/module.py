def retry_delays(attempts, base=1.0, cap=30.0):
    return [base * 2 ** (i + 1) for i in range(attempts)]

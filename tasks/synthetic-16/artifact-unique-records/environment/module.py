def unique_records(records, key):
    return list({row[key]: row for row in records}.values())

def allowed_changes(paths):
    return all(path.startswith('src/') for path in paths)

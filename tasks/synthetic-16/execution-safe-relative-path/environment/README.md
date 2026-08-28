Implement `safe_relative_path(value)`.

Return a normalized POSIX relative path. Reject absolute paths, Windows drive paths, empty paths, and any path that contains or normalizes through `..`. Convert backslashes to slashes and remove `.` components.

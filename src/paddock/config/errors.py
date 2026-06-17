class ConfigError(Exception):
    """Raised when config loading or validation fails.

    Multiple errors from a single resolve pass are aggregated as an ``ExceptionGroup``
    of ``ConfigError`` instances; this class also serves as the leaf exception type.
    """

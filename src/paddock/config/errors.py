class ConfigError(Exception):
    """Raised when config loading or validation fails.

    Multiple errors from a single resolve pass are aggregated as an ``ExceptionGroup``
    of ``ConfigError`` instances; this class also serves as the leaf exception type.
    """


class PaddockEnvironmentError(Exception):
    """Raised when the host environment blocks paddock from running.

    Distinct from :class:`ConfigError`: the configuration is valid, but the
    filesystem/host state (e.g. ``.paddock`` already exists as a file) prevents
    paddock from proceeding.
    """

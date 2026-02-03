
def pg_enum(enum_cls):
    """
    Helper to create an SQLAlchemy Enum that uses the enum values (lowercase)
    instead of names (UPPERCASE) for persistence, matching Postgres enums.
    """
    return SQLEnum(enum_cls, values_callable=lambda x: [e.value for e in x])

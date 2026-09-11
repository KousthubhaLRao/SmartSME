"""Cross-cutting infrastructure: settings, database session, auth, helpers.

Nothing here contains business rules. `core.db` deliberately knows nothing
about the models so that `models` can import it without a cycle; the
declarative `Base` lives in `models.base` instead.
"""

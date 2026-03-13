"""
Calseta — CLI commands.

Management commands that operate directly against the database.
Run from inside the Docker container or any environment with DATABASE_URL set.

Usage:
    python -m app.cli.create_api_key --name admin --scopes admin
    python -m app.cli.list_api_keys
    python -m app.cli.seed_demo_data
    python -m app.cli.rotate_encryption_key
"""

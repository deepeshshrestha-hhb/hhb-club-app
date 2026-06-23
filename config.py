import os

from dotenv import load_dotenv

# Load variables from a local .env file (if present) into os.environ.
# The .env file is gitignored and must never be committed.
load_dotenv()


class Config:
    # Flask secret key - required in production. The dev fallback is only for
    # local convenience and must not be relied on for any deployed instance.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # --- Spond credentials (read from the environment / .env file) ---
    # See .env.example for the variables you need to set. To find your Group ID:
    # log into Spond on the web, open your club's group, and the ID is in the
    # URL, e.g. spond.com/client/group/<GROUP_ID>/...
    SPOND_USERNAME = os.environ.get("SPOND_USERNAME")
    # No fallback for the password on purpose - it must come from the environment.
    SPOND_PASSWORD = os.environ.get("SPOND_PASSWORD")
    SPOND_GROUP_ID = os.environ.get("SPOND_GROUP_ID")

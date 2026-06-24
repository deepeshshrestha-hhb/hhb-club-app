import pandas as pd
from pathlib import Path
from config import Config


DATA_DIR = Path(Config.DATA_DIR)


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_excel(filename, **kwargs):
    ensure_data_dir()
    path = DATA_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, **kwargs)


def save_excel(df, filename):
    ensure_data_dir()
    path = DATA_DIR / filename
    df.to_excel(path, index=False)
    # Push the durable copy back to R2 (no-op when R2 isn't configured).
    from services import r2_service
    r2_service.upload_file(path)

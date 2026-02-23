from pathlib import Path
import getpass
import logging
from logging.handlers import RotatingFileHandler
import re
import sys

import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

ROOT = Path("logistics_task_log")

EXPECTED = [
    "TaskID",
    "UserName",
    "TaskName",
    "TaskCadence",
    "StartTimestampUTC",
    "EndTimestampUTC",
    "DurationSeconds",
    "UploadTimestampUTC",
    "AppVersion",
]


def get_logger() -> logging.Logger:
    user_key = re.sub(r"[^a-z0-9_\-\.]", "", re.sub(r"\s+", "_", getpass.getuser().strip().lower()))
    if not user_key:
        user_key = "unknown_user"
    log_dir = Path(config.LOG_BASE_DIR) / user_key / str(config.LOG_USER_SUBDIR_NAME)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / config.LOG_FILES.get("validate_lake", "validate_lake.log")

    logger = logging.getLogger("validate_lake_script")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=1_048_576,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        logger.addHandler(stream_handler)

    return logger


def main() -> None:
    logger = get_logger()
    logger.info("Validate lake started | root=%s", ROOT)

    bad = 0
    for parquet_file in ROOT.rglob("*.parquet"):
        try:
            schema = pq.read_schema(parquet_file)
            cols = [name for name in schema.names]
            if cols != EXPECTED:
                bad += 1
                logger.warning("[SCHEMA MISMATCH] %s", parquet_file)
                logger.warning("  found:    %s", cols)
                logger.warning("  expected: %s", EXPECTED)
        except Exception as exc:
            bad += 1
            logger.exception("[READ FAIL] %s -> %s", parquet_file, exc)

    logger.info("Validate lake finished | bad_files=%s", bad)


if __name__ == "__main__":
    main()

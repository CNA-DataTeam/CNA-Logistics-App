"""
Startup Check Program
---------------------
Creates a daily parquet file with account data.
- If today's file already exists, do nothing.
- If not, delete all existing files and save a new one.
"""

import getpass
import logging
import pandas as pd
from pathlib import Path
from datetime import date

# Configure logging
LOG_FILE = Path(r"\\therestaurantstore.com\920\Data\Logistics\Task-Tracker\Logs\StartupLogs.txt")

def setup_logging() -> None:
    """Configure logging to write to the log file."""
    # Ensure log directory exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_os_user() -> str:
    """Get the current OS username."""
    return getpass.getuser()


def find_task_tracker_root() -> Path:
    """Find the Task-Tracker root folder from synced SharePoint locations."""
    user = get_os_user()
    roots = [
        Path(f"C:/Users/{user}/clarkinc.biz"),
        Path(f"C:/Users/{user}/OneDrive - clarkinc.biz"),
        Path(f"C:/Users/{user}/OneDrive"),
    ]
    libraries = [
        "Clark National Accounts - Documents",
        "Documents - Clark National Accounts",
    ]
    rel = Path("Logistics and Supply Chain/Logistics Support/Task-Tracker")

    for root in roots:
        for lib in libraries:
            p = root / lib / rel
            if p.exists():
                return p

    raise FileNotFoundError(
        "Task-Tracker folder not found. Make sure CNA SharePoint is synced locally."
    )


def get_paths() -> tuple[Path, Path]:
    """Get the output directory and accounts Excel file paths."""
    task_tracker_root = find_task_tracker_root()
    
    # Use raw string (r"...") for UNC paths to handle backslashes correctly
    output_dir = Path(r"\\therestaurantstore.com\920\Data\Logistics\Task-Tracker\Personnel")
    
    accounts_xlsx = (
        task_tracker_root.parents[2]
        / "Data and Analytics"
        / "Resources"
        / "CNA Personnel - Temporary.xlsx"
    )
    
    return output_dir, accounts_xlsx


def get_todays_filename() -> str:
    """Generate filename with today's date."""
    return f"accounts_{date.today().isoformat()}.parquet"


def todays_file_exists(output_dir: Path) -> bool:
    """Check if today's parquet file already exists."""
    todays_file = output_dir / get_todays_filename()
    return todays_file.exists()


def delete_all_parquet_files(output_dir: Path) -> None:
    """Delete all parquet files in the output directory."""
    for file in output_dir.glob("*.parquet"):
        try:
            file.unlink()
            logging.info(f"Deleted: {file.name}")
        except Exception as e:
            logging.error(f"Error deleting {file.name}: {e}")


def load_accounts(path: Path) -> pd.DataFrame:
    """Load accounts data from Excel file."""
    df = pd.read_excel(path, sheet_name="CNA Personnel", engine="openpyxl")
    
    # Select and clean the required columns
    result = df[["Company Group USE", "CustomerCode"]].copy()
    result["Company Group USE"] = result["Company Group USE"].astype(str).str.strip()
    result["CustomerCode"] = result["CustomerCode"].astype(str).str.strip()
    
    # Remove rows where both columns are NaN (represented as 'nan' after astype)
    result = result[
        (result["Company Group USE"] != "nan") | (result["CustomerCode"] != "nan")
    ]
    
    return result

def save_parquet(df: pd.DataFrame, output_dir: Path) -> Path:
    """Save DataFrame as parquet file with today's date."""
    output_path = output_dir / get_todays_filename()
    df.to_parquet(output_path, index=False)
    return output_path

def log_diagnostics(output_dir: Path, accounts_xlsx: Path) -> None:
    """Log detailed path diagnostics for troubleshooting."""
    logging.info("=" * 60)
    logging.info("PATH DIAGNOSTICS")
    logging.info("=" * 60)
    
    logging.info(f"[Output Directory]")
    logging.info(f"  Path:        {output_dir}")
    logging.info(f"  Resolved:    {output_dir.resolve()}")
    logging.info(f"  Exists:      {output_dir.exists()}")
    logging.info(f"  Is absolute: {output_dir.is_absolute()}")
    
    if output_dir.exists():
        logging.info(f"  Is dir:      {output_dir.is_dir()}")
        files = list(output_dir.glob("*"))
        logging.info(f"  Contents:    {len(files)} items")
        for f in files[:10]:
            logging.info(f"    - {f.name}")
        if len(files) > 10:
            logging.info(f"    ... and {len(files) - 10} more")
    
    logging.info(f"[Accounts Excel File]")
    logging.info(f"  Path:        {accounts_xlsx}")
    logging.info(f"  Resolved:    {accounts_xlsx.resolve()}")
    logging.info(f"  Exists:      {accounts_xlsx.exists()}")
    
    logging.info(f"[Today's Output File]")
    todays_file = output_dir / get_todays_filename()
    logging.info(f"  Filename:    {get_todays_filename()}")
    logging.info(f"  Full path:   {todays_file}")
    logging.info(f"  Exists:      {todays_file.exists()}")
    
    logging.info("=" * 60)

def main() -> None:
    """Main startup check routine."""
    setup_logging()
    
    logging.info(f"Running startup check: {date.today().isoformat()}")
    
    # Get paths dynamically
    output_dir, accounts_xlsx = get_paths()
    
    # Log diagnostics
    log_diagnostics(output_dir, accounts_xlsx)
    
    logging.info(f"Output directory: {output_dir}")
    logging.info(f"Accounts file: {accounts_xlsx}")
    
    # Check if today's file already exists
    if todays_file_exists(output_dir):
        logging.info(f"Today's file already exists: {get_todays_filename()}")
        logging.info("No action required. Exiting.")
        return
    
    logging.info("Today's file not found. Processing...")
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Delete all existing parquet files
    logging.info("Deleting old parquet files...")
    delete_all_parquet_files(output_dir)
    
    # Load data from Excel
    logging.info(f"Loading data from: {accounts_xlsx}")
    df = load_accounts(accounts_xlsx)
    logging.info(f"Loaded {len(df)} records")
    
    # Save new parquet file
    output_path = save_parquet(df, output_dir)
    logging.info(f"Saved: {output_path}")
    
    # Verify the file was created
    logging.info(f"[Post-Save Verification]")
    logging.info(f"  File exists: {output_path.exists()}")
    if output_path.exists():
        logging.info(f"  File size:   {output_path.stat().st_size:,} bytes")
    
    logging.info("Startup check complete.")

if __name__ == "__main__":
    main()
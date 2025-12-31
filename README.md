# Logistics Support Task Tracker

An internal Streamlit application used to track time spent on Logistics
Support tasks. Designed for reliability, repeatability, and ease of use
by non-technical users.

------------------------------------------------------------------------

## Overview

The **Logistics Support Task Tracker** is a local Streamlit application
that allows users to:

-   Select a task and cadence (Daily / Periodic / Weekly)
-   Optionally associate the task with an account
-   Track elapsed time (start / pause / resume / end)
-   Add free-form notes
-   Upload task records as Parquet files to a shared data directory

The application is: - Version-controlled via GitHub - Updated
automatically on every run - Installed once per machine - Launched via
simple batch files

------------------------------------------------------------------------

## Repository Structure

    LogisticsSupportTaskTracker/
    ├── app.py
    ├── requirements.txt
    ├── setup.bat
    ├── Start_Task_Tracker.bat
    ├── .streamlit/
    │   ├── config.toml
    │   └── secrets.toml   # local only, NOT committed
    ├── scripts/
    └── README.md

------------------------------------------------------------------------

## Prerequisites (One-Time)

Before installing the app, ensure the following are available:

-   Windows OS
-   Python 3.10+
-   Git for Windows
-   Access to the GitHub repository

Python and Git must be available on the system PATH.

------------------------------------------------------------------------

## First-Time Installation

### 1. Clone the Repository

Recommended location:

    C:\Projects

``` powershell
git clone https://github.com/CNA-DataTeam/LogisticsSupportTaskTracker.git
```

This creates:

    C:\Projects\Task Tracker

------------------------------------------------------------------------

### 2. Create the Secrets File

Create:

    C:\Projects\Task Tracker\.streamlit\secrets.toml

Example:

``` toml
ROOT_DATA_DIR = "C:/Users/<your_user>/clarkinc.biz/Clark National Accounts - Documents/Logistics and Supply Chain/Logistics Support/Task Tracker"
TASKS_CSV = "tasks.csv"
```

This file is intentionally excluded from Git.

------------------------------------------------------------------------

### 3. Run Setup (One Time)

From:

    C:\Projects\Task Tracker

Double-click:

    setup.bat

This: - Creates the virtual environment - Installs dependencies

------------------------------------------------------------------------

## Running the Application

Double-click:

    Start_Task_Tracker.bat

On every launch, the app:

1.  Pulls the latest code from GitHub
2.  Activates the virtual environment
3.  Starts Streamlit
4.  Automatically opens the browser

------------------------------------------------------------------------

## Update Behavior

-   The app updates automatically on launch
-   If GitHub is unavailable, the local version runs
-   No Git interaction is required by users

------------------------------------------------------------------------

## Data Output

Uploaded tasks are written as Parquet files:

    ROOT_DATA_DIR/
      user=<user_login>/
        year=YYYY/
          month=MM/
            day=DD/
              task_<timestamp>_<id>.parquet

Each record includes: - Task and cadence - User info - Start/end
timestamps (UTC) - Duration (seconds) - Notes - App version

------------------------------------------------------------------------

## Common Issues

### No secrets found

Ensure `secrets.toml` exists in:

    C:\Projects\Task Tracker\.streamlit\

### Virtual environment missing

Re-run:

    setup.bat

------------------------------------------------------------------------

## Design Principles

-   Clone once, pull forever
-   Clear separation between setup and runtime
-   GitHub as single source of truth
-   Safe for non-technical users

------------------------------------------------------------------------

## Versioning

The app version is defined in `app.py`:

``` python
APP_VERSION = "x.y.z"
```

Included in uploaded records.

------------------------------------------------------------------------

## Final Notes

This is an internal productivity tool designed to be predictable,
supportable, and easy to maintain in a corporate Windows environment.

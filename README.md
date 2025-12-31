# Logistics Support Task Tracker

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

Before installing the app, ensure the following are insatalled on your machine:

-   Windows OS
-   Python 3.11.3 (IT Help Needed)
-   Git for Windows
    Ensure the following selections:
    - Git from the command line and also from 3rd-party software
        👉 this is critical (adds Git to PATH)
    - Use bundled OpenSSH
    - Use the OpenSSL library
    - Checkout Windows-style, commit Unix-style line endings
    - Use MinTTY (default terminal)
-   Access to the GitHub repository

Python and Git must be available on the system PATH (Check with IT).

------------------------------------------------------------------------

## First-Time Installation

### 1. Clone the Repository

The application is designed to live in a standard location on your
machine.

### Step 1 --- Create the Projects folder

1.  Open **File Explorer**
2.  Navigate to **Local Disk (C:)**
3.  Right-click → **New → Folder**
4.  Name the folder:

    Projects

You should now have:

    C:\Projects

------------------------------------------------------------------------

### Step 2 --- Open a terminal in the Projects folder

1.  Open the `C:\Projects` folder
2.  Hold **Shift**
3.  Right-click inside the folder
4.  Select **"Open PowerShell window here"** or **"Open in Terminal"**

A terminal window should open with the path set to:

    C:\Projects>

------------------------------------------------------------------------

### Step 3 --- Clone the repository

In the terminal, run:

``` powershell
git clone https://github.com/CNA-DataTeam/LogisticsSupportTaskTracker.git
```

This will download the application from GitHub and create a new folder:

    C:\Projects\Task Tracker

This folder contains: - the Streamlit application - setup and launch
scripts - all required configuration files

Once this step is complete, you are ready to proceed with setup.

------------------------------------------------------------------------

### 2. Create the Secrets File

Create:

    C:\Projects\Task Tracker\.streamlit\secrets.toml

Example:

``` toml
ROOT_DATA_DIR = "Link of Clark National Accounts Sharepoint folder" (connect with Luca)
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

## Common Issues

### No secrets found

Ensure `secrets.toml` exists in:

    C:\Projects\Task Tracker\.streamlit\

### Virtual environment missing

Re-run:

    setup.bat

------------------------------------------------------------------------

## Versioning

The app version is defined in `app.py`:

``` python
APP_VERSION = "x.y.z"
```

Included in uploaded records.

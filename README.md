# Logistics Support Task Tracker

## Overview

The **Logistics Support Task Tracker** is a local Streamlit application used to track logistics support work.

Users can:
- Select a task and cadence (Daily / Weekly / Periodic)
- Optionally associate a task with an account
- Track elapsed time (start / pause / resume / end)
- Add notes
- Upload task records to a shared data location

The app:
- Runs locally on each user’s machine  
- Updates automatically on launch  
- Is started by double-clicking batch files  
- Requires no command-line or Git usage by users  

---

## What You Need Installed (One Time)

You must have the following installed on your machine:

- **Python 3.11.x** (installed system-wide and on PATH)
- **Git for Windows** (installed and on PATH)

If any of these are missing, contact IT.

---

## First-Time Setup (One Time)

1. Create a folder anywhere on your machine
   (recommended: `C:\Users\yourusername\TaskTracker`)

2. Copy these two files into that folder:
   - `setup.bat`
   - `Start_Task_Tracker.bat`

3. Double-click:
setup.bat

This will:
- Download the app from GitHub
- Create a local Python environment
- Install all required dependencies

---

## Running the Application

To start the app, double-click:
Start_Task_Tracker.bat

On every launch, the app:
- Checks for updates automatically
- Starts the application
- Opens your browser

---

## Secrets File (Required)

Each user must have this file:
App.streamlit\secrets.toml

This file is local only and not shared.

---

## Common Fixes

- App does not start → Run `setup.bat` again  
- Browser does not open → Go to `http://localhost:8501`

---

## Important Notes

- Do **not** edit files inside the `App` folder  
- Do **not** use Git manually  
- Do **not** share your App folder with other users  

That’s it. Double-click to use.

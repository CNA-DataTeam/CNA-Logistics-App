import streamlit as st
import config

# Define pages and their grouping for navigation
pages = {
    "Home": [
        st.Page("pages/home.py", title="Home"),
    ],
    "Tasks": [
        st.Page("pages/task-tracker.py", title="Tracker"),
        st.Page("pages/task-tracker-analytics.py", title="Analytics"),
    ],
}

# Initialize and run the navigation
navigation = st.navigation(pages)
navigation.run()
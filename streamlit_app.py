import streamlit as st
import pandas as pd
import datetime
import io
import logging
from sqlalchemy.orm import Session

# Configure logging (optional but good for debugging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Imports (adjust if needed based on final structure) ---
# Assuming running Streamlit from project root, imports from src should work
from src.database import crud, models
from src.database.connection import get_db, SessionLocal

# --- Reporting Function Import ---
from src.reporting.excel_generator import generate_summary_report

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Steam Review Analyzer")

# --- Page Navigation --- 
page = st.sidebar.radio("Navigate", ["Report Generator", "Settings"])
st.sidebar.divider()

# --- Helper Functions --- 
@st.cache_data # Cache the list of apps for the session
def get_app_list_for_dropdown():
    logger.info("Fetching tracked app list for dropdown...")
    db: Session = SessionLocal() # Use SessionLocal directly for caching
    try:
        apps = crud.get_active_tracked_apps(db) # Only show active apps in report dropdown
        app_dict = {app[1] if app[1] else f"AppID: {app[0]}": app[0] for app in apps}
        return app_dict
    finally:
        db.close()

@st.cache_data # Also cache all apps for settings page
def get_all_apps_for_settings():
    logger.info("Fetching ALL tracked apps for settings...")
    db: Session = SessionLocal()
    try:
        return crud.get_all_tracked_apps(db)
    finally:
        db.close()

def get_last_update(app_id: int):
    logger.info(f"Fetching last update time for app {app_id}")
    db: Session = SessionLocal()
    try:
        timestamp = crud.get_app_last_update_time(db, app_id)
        return timestamp
    except Exception as e:
        logger.error(f"Error fetching last update time in Streamlit: {e}")
        return None
    finally:
        db.close()

# --- Page Implementations --- 

if page == "Report Generator":
    st.header("Report Generator")
    st.write("Select an application and a start date to generate an Excel report.")

    # --- App Selection --- 
    st.subheader("1. Select Application")
    app_data = get_app_list_for_dropdown()
    if not app_data:
        st.warning("No *active* tracked applications found in the database. Check Settings or add apps.")
        st.stop()

    selected_app_name = st.selectbox(
        label="Select Game:",
        options=list(app_data.keys())
    )
    selected_app_id = app_data.get(selected_app_name)

    if selected_app_id:
        st.write(f"Selected App ID: `{selected_app_id}`")
        # --- Display Last Update Time ---
        last_update_ts = get_last_update(selected_app_id)
        if last_update_ts and last_update_ts > 0:
            last_update_dt = datetime.datetime.fromtimestamp(last_update_ts, tz=datetime.timezone.utc)
            st.caption(f"Data current as of: {last_update_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            st.caption("Data current as of: Never fetched (or timestamp is 0)")
    else:
         st.write("App ID not found for selection.")

    # --- Date Selection ---
    st.subheader("2. Select Start Date")
    default_start_date = datetime.date.today() - datetime.timedelta(days=30)
    selected_date = st.date_input(
        label="Generate report for reviews SINCE this date (inclusive):",
        value=default_start_date
    )

    # --- Report Generation ---
    st.subheader("3. Generate Report")
    if st.button("Generate & Download Excel Report", key="generate_button"):
        if selected_app_id and selected_date:
            st.info(f"Generating report for '{selected_app_name}' (ID: {selected_app_id}) for reviews since {selected_date}...")
            
            # Convert selected date to Unix timestamp (start of day, UTC)
            start_datetime_utc = datetime.datetime.combine(selected_date, datetime.time.min, tzinfo=datetime.timezone.utc)
            start_timestamp = int(start_datetime_utc.timestamp())
            
            logger.info(f"Calling report generator for app {selected_app_id} since timestamp {start_timestamp}")
            
            try:
                with st.spinner("Generating report... Fetching data, calling AI, building Excel file..."):
                    report_bytes = generate_summary_report(selected_app_id, start_timestamp)
                
                st.success("Report generated successfully!")
                
                # Create filename
                filename = f"SteamAnalysis_{selected_app_id}_{selected_app_name.replace(' ', '_')}_Since_{selected_date.strftime('%Y%m%d')}.xlsx"
                
                st.download_button(
                    label="Download Excel Report",
                    data=report_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                logger.exception(f"Error during report generation triggered by Streamlit: {e}")
                st.error(f"Failed to generate report: {e}")
                # Optionally show more details if needed for debugging
                # st.exception(e)
            
        else:
            st.warning("Please select an application and a start date.")

elif page == "Settings":
    st.header("Settings - Manage Tracked Applications")

    # --- Display Current Apps --- 
    st.subheader("Currently Tracked Apps")
    all_apps = get_all_apps_for_settings()
    
    if not all_apps:
        st.info("No applications are currently being tracked.")
    else:
        cols = st.columns([1, 3, 1, 1]) # Adjust column widths
        cols[0].write("**App ID**")
        cols[1].write("**Name**")
        cols[2].write("**Is Active?**")
        cols[3].write("**Last Fetched (UTC)**")
        st.divider()

        for app in all_apps:
            cols = st.columns([1, 3, 1, 1])
            cols[0].write(f"`{app.app_id}`")
            cols[1].write(app.name if app.name else "*N/A*")
            
            # Checkbox for toggling active status
            is_active = cols[2].checkbox("Active", value=app.is_active, key=f"active_{app.app_id}", label_visibility="collapsed")
            if is_active != app.is_active: # Check if checkbox state changed
                db = SessionLocal()
                try:
                    crud.update_app_active_status(db, app.app_id, is_active)
                    st.success(f"App {app.app_id} status updated!")
                    # Clear caches to reflect changes
                    st.cache_data.clear()
                    st.rerun() # Rerun to refresh the display immediately
                except Exception as e:
                    st.error(f"Failed to update status for app {app.app_id}: {e}")
                finally:
                     db.close()

            # Display last fetched time
            if app.last_fetched_timestamp and app.last_fetched_timestamp > 0:
                dt = datetime.datetime.fromtimestamp(app.last_fetched_timestamp, tz=datetime.timezone.utc)
                cols[3].write(dt.strftime("%Y-%m-%d %H:%M"))
            else:
                 cols[3].write("Never")
            st.divider()

    # --- Add New App --- 
    st.subheader("Add New App to Track")
    with st.form(key="add_app_form"):
        new_app_id_str = st.text_input("Steam App ID:")
        new_app_name = st.text_input("Game Name (Optional):")
        submitted = st.form_submit_button("Add App")
        
        if submitted:
            if not new_app_id_str or not new_app_id_str.isdigit():
                st.error("Please enter a valid numerical App ID.")
            else:
                new_app_id = int(new_app_id_str)
                db = SessionLocal()
                try:
                    # Optional: Add check if app already exists? crud function handles conflict.
                    crud.add_tracked_app(db, new_app_id, new_app_name if new_app_name else None)
                    st.success(f"Attempted to add App ID {new_app_id}. Refreshing list...")
                    # Clear caches and rerun
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add app {new_app_id}: {e}")
                finally:
                    db.close()

# --- Footer --- 
st.sidebar.divider()
st.sidebar.caption("Steam Review Analysis Tool V1") 
import streamlit as st
import pandas as pd
import datetime
import io
import logging
import asyncio
from sqlalchemy.orm import Session
from typing import List
from datetime import timezone, timedelta
from contextlib import contextmanager # Import contextmanager

# Configure logging (optional but good for debugging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Imports (adjust if needed based on final structure) ---
# Assuming running Streamlit from project root, imports from src should work
from src.database import crud, models
from src.database.connection import get_db, SessionLocal
from src.database import crud_youtube # Import YouTube CRUD
from src.database.models import YouTubeChannel, GameInfluencerMapping # Import YouTube models if needed directly
from src.youtube.supadata_client import SupadataClient # Import Supadata client

# --- Reporting Function Import ---
from src.reporting.excel_generator import generate_summary_report # For Steam
from src.reporting.youtube_report_generator import generate_youtube_summary_report # For YouTube

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Feedback Analyzer") # More general title

# --- Page Navigation --- 
page = st.sidebar.radio("Navigate", ["Steam Report Generator", "Steam Settings", "YouTube Management", "YouTube Feedback Viewer"])
st.sidebar.divider()

# --- Helper Functions --- 
@st.cache_data # Cache the list of apps for the session
def get_app_list_for_dropdown():
    logger.info("Fetching tracked app list for dropdown...")
    db: Session = SessionLocal() # Use SessionLocal directly for caching
    try:
        # Now gets full TrackedApp objects
        apps: List[models.TrackedApp] = crud.get_active_tracked_apps(db) 
        # Extract name and app_id into the dictionary
        app_dict = {app.name if app.name else f"AppID: {app.app_id}": app.app_id for app in apps}
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

# --- Database Session Handling (Revised) ---
# Get session when needed, ensure closure
@contextmanager # Use the correct decorator
def get_db_session():
    db = None
    db_gen = get_db()
    try:
        db = next(db_gen)
        yield db
    finally:
        if db:
            try:
                next(db_gen)
            except StopIteration:
                pass
            except Exception as e:
                logger.error(f"Error closing DB session in context manager: {e}")

# --- Page Implementations --- 

if page == "Steam Report Generator":
    st.header("Steam Report Generator")
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
            
            logger.info(f"Calling async report generator for app {selected_app_id} since timestamp {start_timestamp}")
            
            try:
                # Use a spinner while the async function runs
                with st.spinner("Generating report... Fetching data, calling AI concurrently, building Excel file..."):
                    # Run the async function using asyncio.run()
                    report_bytes = asyncio.run(generate_summary_report(selected_app_id, start_timestamp))
                
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
                logger.exception(f"Error during async report generation triggered by Streamlit: {e}")
                st.error(f"Failed to generate report: {e}")
                # Optionally show more details if needed for debugging
                # st.exception(e)
            
        else:
            st.warning("Please select an application and a start date.")

elif page == "Steam Settings":
    st.header("Settings - Manage Tracked Steam Applications")

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

elif page == "YouTube Management":
    st.header("Manage Tracked YouTube Games & Influencers")
    
    # Use the context manager for DB session
    with get_db_session() as db_session:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Games")
            # Display existing games
            try:
                # Assuming crud_youtube.get_active_games exists and works
                active_games = crud_youtube.get_active_games(db_session)
                if active_games:
                    games_df = pd.DataFrame([(g.id, g.name, g.steam_app_id, g.slack_channel_id, g.is_active) for g in active_games], 
                                            columns=["ID", "Name", "Steam App ID", "Slack Channel ID", "Is Active"])
                    # TODO: Add edit/deactivate functionality here later
                    st.dataframe(games_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No active games found in the database.")
            except Exception as e:
                st.error(f"Error fetching active games: {e}")

            # Form to add a new game
            with st.expander("Add New Game"):
                with st.form("add_game_form", clear_on_submit=True):
                    new_game_name = st.text_input("Game Name", key="new_game_name_yt") # Unique key
                    new_steam_id_str = st.text_input("Steam App ID (Optional)", key="new_steam_id_yt")
                    new_slack_id = st.text_input("Slack Channel ID (Optional, e.g., C1234567)", key="new_slack_id_yt")
                    
                    submitted = st.form_submit_button("Add Game")
                    if submitted:
                        if not new_game_name:
                            st.warning("Game Name is required.")
                        else:
                            new_steam_id = None
                            if new_steam_id_str:
                                try:
                                    new_steam_id = int(new_steam_id_str)
                                except ValueError:
                                    st.error("Invalid Steam App ID. Please enter a number.")
                                    new_game_name = None 
                            
                            if new_game_name:
                                try:
                                    # Use the db_session from the context manager
                                    added_game = crud_youtube.add_game(db_session, 
                                                               name=new_game_name, 
                                                               steam_app_id=new_steam_id, 
                                                               slack_channel_id=new_slack_id or None)
                                    if added_game:
                                        st.success(f"Game '{added_game.name}' added successfully!")
                                        st.rerun()
                                    else:
                                        # Check if exists using correct module and model
                                        existing = db_session.query(crud_youtube.Game).filter(crud_youtube.Game.name == new_game_name).first()
                                        if existing:
                                             st.warning(f"Game '{new_game_name}' already exists.")
                                        else:
                                             st.error("Failed to add game (unknown reason, check logs).")
                                except Exception as e:
                                    st.error(f"Error adding game: {e}")
                                    logger.exception("Error adding game via Streamlit UI")

        with col2:
            st.subheader("Influencers & Channels")
            # Display existing influencers
            try:
                all_influencers = db_session.query(crud_youtube.Influencer).order_by(crud_youtube.Influencer.name).all()
                if all_influencers:
                    influencer_df = pd.DataFrame([(i.id, i.name, i.notes) for i in all_influencers],
                                                 columns=["ID", "Name", "Notes"])
                    # TODO: Add Edit/Delete Influencer functionality
                    st.dataframe(influencer_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No influencers found in the database.")
            except Exception as e:
                st.error(f"Error fetching influencers: {e}")
            
            # Form to add a new influencer
            with st.expander("Add New Influencer"):
                with st.form("add_influencer_form", clear_on_submit=True):
                    new_influencer_name = st.text_input("Influencer Name", key="new_influencer_name_yt")
                    new_influencer_notes = st.text_area("Notes (Optional)", key="new_influencer_notes_yt")
                    
                    submitted_infl = st.form_submit_button("Add Influencer")
                    if submitted_infl:
                        if not new_influencer_name:
                            st.warning("Influencer Name is required.")
                        else:
                            try:
                                # Corrected module
                                added_influencer = crud_youtube.add_influencer(db_session, 
                                                                      name=new_influencer_name, 
                                                                      notes=new_influencer_notes or None)
                                if added_influencer:
                                    st.success(f"Influencer '{added_influencer.name}' added successfully!")
                                    st.rerun()
                                else:
                                    # Check if exists using correct module and model
                                    existing = db_session.query(crud_youtube.Influencer).filter(crud_youtube.Influencer.name == new_influencer_name).first()
                                    if existing:
                                        st.warning(f"Influencer '{new_influencer_name}' already exists.")
                                    else:
                                        st.error("Failed to add influencer (unknown reason, check logs).")
                            except Exception as e:
                                st.error(f"Error adding influencer: {e}")
                                logger.exception("Error adding influencer via Streamlit UI")
            
            # Channel Management (Uses all_influencers initialized above)
            st.divider()
            st.subheader("Manage Channels for Influencer")
            
            if not all_influencers: # Check the initialized variable
                st.warning("Add an influencer first to manage their channels.")
            else:
                influencer_options = {f"{inf.name} (ID: {inf.id})": inf.id for inf in all_influencers}
                selected_influencer_display = st.selectbox("Select Influencer:", options=list(influencer_options.keys()), key="select_influencer_channel")
                selected_influencer_id = influencer_options.get(selected_influencer_display)

                if selected_influencer_id:
                    # Display existing channels for the selected influencer
                    st.markdown("**Existing Channels:**")
                    try:
                        # Corrected module
                        influencer_channels = crud_youtube.get_channels_by_influencer_id(db_session, selected_influencer_id)
                        if influencer_channels:
                            chan_df = pd.DataFrame([(c.id, c.channel_name, c.handle, c.last_checked_timestamp) for c in influencer_channels],
                                                   columns=["Channel ID", "Name", "Handle", "Last Checked TS"])
                            # Convert timestamp to readable date
                            chan_df['Last Checked'] = pd.to_datetime(chan_df['Last Checked TS'], unit='s', errors='coerce', utc=True).dt.strftime('%Y-%m-%d %H:%M UTC')
                            st.dataframe(chan_df[["Channel ID", "Name", "Handle", "Last Checked"]], hide_index=True, use_container_width=True)
                        else:
                            st.info("No channels found for this influencer.")
                    except Exception as e:
                        st.error(f"Error fetching channels: {e}")

                    # Form to add/update a channel
                    with st.expander("Add or Update Channel for Selected Influencer"):
                        with st.form("add_channel_form", clear_on_submit=True):
                            # Changed input field
                            channel_input = st.text_input("Channel Handle (e.g., @handle) or Full URL", key="add_channel_input")
                            # channel_id_uc = st.text_input("YouTube Channel ID (UC... string)", key="add_channel_id") # Removed old ID input
                            channel_name = st.text_input("Channel Name (Optional - will fetch if blank)", key="add_channel_name")
                            # channel_handle = st.text_input("Channel Handle (Optional, e.g., @handle)", key="add_channel_handle") # Removed old handle input, will get from input/API
                            
                            submitted_chan = st.form_submit_button("Add/Update Channel by Handle/URL")
                            if submitted_chan:
                                if not channel_input:
                                    st.warning("Channel Handle or URL is required.")
                                else:
                                    # Attempt to extract handle (simple extraction for @handle format)
                                    extracted_handle = None
                                    if channel_input.startswith('@'):
                                        extracted_handle = channel_input.strip()
                                    elif "youtube.com/@" in channel_input:
                                         try:
                                             # Extract handle part after /@
                                             handle_part = channel_input.split("youtube.com/@")[1]
                                             extracted_handle = "@" + handle_part.split('/')[0].split('?')[0]
                                         except IndexError:
                                             st.warning("Could not parse handle from URL.")
                                    else:
                                        # Assume input might be the handle without @ if it doesn't look like a URL
                                        if not ('/' in channel_input or '.' in channel_input):
                                             extracted_handle = "@" + channel_input.strip()
                                        else:
                                             st.warning("Input format not recognized as @handle or youtube.com/@... URL. Please use the @handle format.")

                                    if extracted_handle:
                                        logger.info(f"Extracted handle '{extracted_handle}' from input '{channel_input}'. Attempting lookup.")
                                        try:
                                            # Use the Supadata client to look up details by handle
                                            with st.spinner(f"Looking up channel details for {extracted_handle}..."):
                                                 # Need to instantiate client within the context if not already available
                                                 client = SupadataClient() # Assumes API key is in env
                                                 channel_details = client.get_channel_details_by_handle(extracted_handle)
                                            
                                            if channel_details and 'id' in channel_details:
                                                uc_channel_id = channel_details['id']
                                                api_channel_name = channel_details.get('name')
                                                api_channel_handle = channel_details.get('handle') # Should match input or be derived
                                                
                                                st.info(f"Found Channel ID: {uc_channel_id}, Name: {api_channel_name}, Handle: {api_channel_handle}")

                                                # Use fetched details if user left fields blank
                                                final_channel_name = channel_name or api_channel_name
                                                # Prefer the input handle if provided, fallback to API, then None
                                                final_handle = extracted_handle # Use the one we looked up

                                                # Now add/update using the fetched UC... ID
                                                added_channel = crud_youtube.add_or_update_channel(
                                                    db=db_session,
                                                    channel_id=uc_channel_id,
                                                    influencer_id=selected_influencer_id,
                                                    channel_name=final_channel_name,
                                                    handle=final_handle
                                                )
                                                if added_channel:
                                                    st.success(f"Channel '{uc_channel_id}' ({final_channel_name or 'N/A'}) added/updated for influencer ID {selected_influencer_id}.")
                                                    st.rerun()
                                                else:
                                                    st.error("Failed to add/update channel in DB (check logs for details).")
                                            else:
                                                st.error(f"Could not find channel details or ID via Supadata API for handle '{extracted_handle}'. Please verify handle/URL or try entering the UC... ID manually if known.")
                                        except Exception as e:
                                            st.error(f"Error looking up or adding/updating channel: {e}")
                                            logger.exception("Error during channel lookup/add via Streamlit UI")
                                    # else: warning already shown if handle couldn't be extracted
            
        st.divider()
        st.subheader("Game <-> Influencer Mapping")
        
        # Display Existing Mappings
        try:
            # Corrected module
            all_mappings = crud_youtube.get_all_game_influencer_mappings(db_session)
            if all_mappings:
                # Prepare data for display
                display_data = []
                for m in all_mappings:
                    display_data.append({
                        "game_id": m.game_id,
                        "influencer_id": m.influencer_id,
                        "Game Name": m.game.name if m.game else "N/A",
                        "Influencer Name": m.influencer.name if m.influencer else "N/A",
                        "Is Active": m.is_active
                    })
                mappings_df = pd.DataFrame(display_data)
                
                st.markdown("**Existing Mappings:**")
                # Use st.data_editor to allow editing the 'Is Active' status directly
                edited_df = st.data_editor(
                    mappings_df[["Game Name", "Influencer Name", "Is Active"]], 
                    key="mappings_editor",
                    disabled=["Game Name", "Influencer Name"], # Don't allow editing names here
                    hide_index=True,
                    use_container_width=True
                )
                
                # Check for changes in the edited dataframe compared to original
                if not mappings_df["Is Active"].equals(edited_df["Is Active"]):
                    diff_indices = mappings_df.index[mappings_df["Is Active"] != edited_df["Is Active"]]
                    for idx in diff_indices:
                         original_row = mappings_df.iloc[idx]
                         edited_row = edited_df.iloc[idx]
                         game_id_to_update = original_row['game_id']
                         influencer_id_to_update = original_row['influencer_id']
                         new_status = edited_row['Is Active']
                         
                         logger.info(f"Detected status change for ({game_id_to_update}, {influencer_id_to_update}) to {new_status}")
                         try:
                              # Corrected module
                              updated = crud_youtube.update_mapping_active_status(db_session, game_id_to_update, influencer_id_to_update, new_status)
                              if updated:
                                   st.success(f"Mapping status updated for {original_row['Game Name']} <-> {original_row['Influencer Name']} to {new_status}")
                                   st.rerun()
                              else:
                                   st.error("Failed to update mapping status in DB.")
                         except Exception as e:
                              st.error(f"Error updating mapping status: {e}")
                              logger.exception("Error updating mapping status via Streamlit UI")
            else:
                st.info("No mappings found.")

        except Exception as e:
            st.error(f"Error fetching mappings: {e}")
            logger.exception("Error fetching mappings for Streamlit UI")

        # Add New Mapping
        st.markdown("**Add New Mapping:**")
        try:
            # Corrected module
            all_games = crud_youtube.get_active_games(db_session)
            all_influencers_map_add = db_session.query(crud_youtube.Influencer).order_by(crud_youtube.Influencer.name).all() # Renamed variable
            
            if not all_games:
                 st.warning("No active games available to create mapping.")
            elif not all_influencers_map_add:
                 st.warning("No influencers available to create mapping.")
            else:
                 game_options = {f"{g.name} (ID: {g.id})": g.id for g in all_games}
                 influencer_options_map_add = {f"{i.name} (ID: {i.id})": i.id for i in all_influencers_map_add}
                 
                 col_map1, col_map2, col_map3 = st.columns([2,2,1])
                 with col_map1:
                     selected_game_display_map = st.selectbox("Select Game:", options=list(game_options.keys()), key="map_game_select")
                 with col_map2:
                     selected_influencer_display_map = st.selectbox("Select Influencer:", options=list(influencer_options_map_add.keys()), key="map_influencer_select")
                 with col_map3:
                    st.write("&nbsp;") # Spacer
                    if st.button("Add Mapping", key="add_mapping_button"):
                        game_id_map = game_options.get(selected_game_display_map)
                        influencer_id_map = influencer_options_map_add.get(selected_influencer_display_map)
                        
                        if game_id_map and influencer_id_map:
                             try:
                                 # Corrected module
                                 added_mapping = crud_youtube.add_game_influencer_mapping(db_session, game_id_map, influencer_id_map, is_active=True)
                                 if added_mapping:
                                     st.success(f"Mapping added for Game ID {game_id_map} <-> Influencer ID {influencer_id_map}.")
                                     st.rerun()
                                 else:
                                     # Check if exists using correct model
                                     existing = db_session.query(crud_youtube.GameInfluencerMapping).filter_by(game_id=game_id_map, influencer_id=influencer_id_map).first()
                                     if existing:
                                         st.warning("Mapping already exists.")
                                         if not existing.is_active:
                                             # Option to reactivate?
                                             # Making this automatic for now for simplicity
                                             logger.info(f"Attempting to reactivate existing mapping for ({game_id_map}, {influencer_id_map})")
                                             # Corrected module
                                             reactivated = crud_youtube.update_mapping_active_status(db_session, game_id_map, influencer_id_map, True)
                                             if reactivated:
                                                 st.success("Existing inactive mapping reactivated.")
                                                 st.rerun()
                                             else:
                                                 st.error("Failed to reactivate existing mapping.")
                                     else:
                                         st.error("Failed to add mapping.")
                             except Exception as e:
                                 st.error(f"Error adding mapping: {e}")
                                 logger.exception("Error adding mapping via Streamlit UI")
                        else:
                            st.error("Failed to get selected Game or Influencer ID.")
        except Exception as e:
             st.error(f"Error loading games/influencers for mapping form: {e}")

elif page == "YouTube Feedback Viewer":
    st.header("View Analyzed YouTube Feedback")
    # TODO: Implement Feedback viewing UI (Selectors, Display, Download)
    # st.write("Feedback Viewer UI Placeholder")

    with get_db_session() as db_session:
        try:
            # --- 1. Selectors --- 
            col_select1, col_select2 = st.columns(2)
            
            with col_select1:
                 st.subheader("1. Select Game")
                 active_games_yt = crud_youtube.get_active_games(db_session)
                 if not active_games_yt:
                     st.warning("No active games found. Please add games in the Management tab.")
                     st.stop()
                 
                 game_options_yt = {f"{g.name} (ID: {g.id})": g.id for g in active_games_yt}
                 selected_game_display_yt = st.selectbox("Select Game:", options=list(game_options_yt.keys()), key="yt_viewer_game_select")
                 selected_game_id_yt = game_options_yt.get(selected_game_display_yt)

            with col_select2:
                 st.subheader("2. Select Date Range")
                 # Default to last 7 days
                 today = datetime.datetime.now(timezone.utc).date()
                 default_start = today - timedelta(days=7)
                 date_range = st.date_input(
                     "Select Date Range:",
                     value=(default_start, today),
                     key="yt_viewer_date_range"
                 )
                 
                 start_date_yt = None
                 end_date_yt = None
                 if len(date_range) == 2:
                     start_date_yt = datetime.datetime.combine(date_range[0], datetime.time.min, tzinfo=timezone.utc)
                     # Add one day to end date to make it inclusive up to the end of that day
                     end_date_yt = datetime.datetime.combine(date_range[1] + timedelta(days=1), datetime.time.min, tzinfo=timezone.utc)
                 else:
                     st.warning("Please select a valid date range.")

            # --- 2. Load Data Button --- 
            st.divider()
            st.subheader("3. Load & View Feedback")
            
            # Initialize session state for feedback data
            if 'youtube_feedback_data' not in st.session_state:
                st.session_state.youtube_feedback_data = None
            if 'youtube_feedback_params' not in st.session_state:
                st.session_state.youtube_feedback_params = {}

            if st.button("Load Analyzed Feedback", key="load_yt_feedback_btn"):
                if selected_game_id_yt and start_date_yt and end_date_yt:
                    with st.spinner("Fetching analyzed feedback..."):
                        try:
                            # Fetch data from DB
                            feedback_data = crud_youtube.get_analyzed_feedback_for_game(db_session, selected_game_id_yt, start_date_yt, end_date_yt)
                            st.session_state.youtube_feedback_data = feedback_data
                            # Store params used to fetch this data
                            st.session_state.youtube_feedback_params = {
                                'game_id': selected_game_id_yt,
                                'game_name': selected_game_display_yt,
                                'start_date': start_date_yt,
                                'end_date': end_date_yt
                            }
                            if not feedback_data:
                                st.info("No analyzed feedback found for the selected game and date range.")
                            else:
                                st.success(f"Loaded {len(feedback_data)} feedback records.")
                        except Exception as e:
                            st.error(f"Error fetching feedback data: {e}")
                            logger.exception("Error fetching YouTube feedback for viewer")
                            st.session_state.youtube_feedback_data = None
                            st.session_state.youtube_feedback_params = {}
                else:
                    st.warning("Please select a game and a valid date range.")
            
            # --- 3. Display Data --- 
            if st.session_state.youtube_feedback_data is not None:
                feedback_to_display = st.session_state.youtube_feedback_data
                params = st.session_state.youtube_feedback_params
                st.markdown(f"#### Displaying Feedback for: {params.get('game_name', 'N/A')}")
                st.caption(f"Period: {params.get('start_date', datetime.datetime.now()).strftime('%Y-%m-%d')} to { (params.get('end_date', datetime.datetime.now()) - timedelta(days=1)).strftime('%Y-%m-%d') }")

                if not feedback_to_display:
                     st.info("No analyzed feedback found for the selected criteria.")
                else:
                    # Display using expanders
                    for item in feedback_to_display:
                         header = f"**{item.get('video_title', 'N/A')}** by {item.get('influencer_name', 'N/A')} ({item.get('channel_handle', 'N/A')}) | Sentiment: {item.get('analyzed_sentiment', 'N/A')} | Uploaded: {item.get('video_upload_date', 'N/A').strftime('%Y-%m-%d')}"
                         with st.expander(header):
                             st.markdown("**Summary & Analysis:**")
                             st.markdown(item.get('summary', 'No summary available.')) # Display markdown summary
                             
                             # Optionally display themes/bugs/etc. in columns
                             col_disp1, col_disp2 = st.columns(2)
                             with col_disp1:
                                 st.write("**Positive Themes:**")
                                 pos_themes = item.get('positive_themes')
                                 st.caption('\n'.join(map(str, pos_themes)) if pos_themes and isinstance(pos_themes, list) else '-')
                                 st.write("**Bug Reports:**")
                                 bugs = item.get('bug_reports')
                                 st.caption('\n'.join(map(str, bugs)) if bugs and isinstance(bugs, list) else '-')
                                 st.write("**Gameplay Loop:**")
                                 gameplay = item.get('gameplay_loop_feedback')
                                 st.caption('\n'.join(map(str, gameplay)) if gameplay and isinstance(gameplay, list) else '-')
                             with col_disp2:
                                 st.write("**Negative Themes:**")
                                 neg_themes = item.get('negative_themes')
                                 st.caption('\n'.join(map(str, neg_themes)) if neg_themes and isinstance(neg_themes, list) else '-')
                                 st.write("**Feature Requests:**")
                                 features = item.get('feature_requests')
                                 st.caption('\n'.join(map(str, features)) if features and isinstance(features, list) else '-')
                                 st.write("**Balance Feedback:**")
                                 balance = item.get('balance_feedback')
                                 st.caption('\n'.join(map(str, balance)) if balance and isinstance(balance, list) else '-')
                                 st.write("**Monetization:**")
                                 monetization = item.get('monetization_feedback')
                                 st.caption('\n'.join(map(str, monetization)) if monetization and isinstance(monetization, list) else '-')
                                 
                             st.divider()
                             st.caption(f"Video ID: {item.get('video_id')} | Analyzed: {item.get('llm_analysis_timestamp', 'N/A')}")
                    
                    st.divider()
                    st.subheader("4. Download Report")
                    # --- 4. Download Button --- 
                    if st.button("Generate Excel Report for this View", key="yt_download_btn"):
                        params = st.session_state.youtube_feedback_params
                        dl_game_id = params.get('game_id')
                        dl_start_date = params.get('start_date')
                        # Adjust end date back for report generation (it was incremented for the query)
                        dl_end_date = params.get('end_date') - timedelta(days=1)
                        dl_game_name = params.get('game_name', f'Game_{dl_game_id}').split(' (')[0].replace(' ', '_')

                        if dl_game_id and dl_start_date and dl_end_date:
                            with st.spinner("Generating Excel report..."):
                                try:
                                    # Need to re-get a DB session as the previous one might be closed
                                    # The reporting function is async, so we need to run it
                                    async def generate_and_get_bytes():
                                         with get_db_session() as report_db_session:
                                             return await generate_youtube_summary_report(report_db_session, dl_game_id, dl_start_date, dl_end_date)
                                    
                                    report_bytes = asyncio.run(generate_and_get_bytes())
                                    
                                    if report_bytes:
                                        st.success("Excel report generated!")
                                        dl_filename = f"YouTube_Feedback_{dl_game_name}_{dl_start_date.strftime('%Y%m%d')}-{dl_end_date.strftime('%Y%m%d')}.xlsx"
                                        st.download_button(
                                            label="Download Excel Report",
                                            data=report_bytes,
                                            file_name=dl_filename,
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                        )
                                    else:
                                        st.error("Failed to generate Excel report (generator returned None).")
                                except Exception as e:
                                    st.error(f"Error generating Excel report: {e}")
                                    logger.exception("Error generating YouTube Excel report from viewer")
                        else:
                             st.error("Cannot generate report, parameters from loaded data are missing.")

        except Exception as e:
             st.error(f"An error occurred in the YouTube Feedback Viewer: {e}")
             logger.exception("Error in Streamlit YouTube Feedback Viewer tab")

# --- Footer --- 
st.sidebar.divider()
st.sidebar.caption("Feedback Analyzer V1.1") # Updated version 
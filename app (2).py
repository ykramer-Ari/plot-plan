import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from datetime import datetime
import json
import sqlite3
from pathlib import Path

# Set page config
st.set_page_config(
    page_title="Plot Plan Reader",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
        padding: 10px;
        border-radius: 8px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 8px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Database setup
def init_db():
    conn = sqlite3.connect("projects.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            address TEXT,
            block TEXT,
            lot TEXT,
            sidewalk_sf REAL,
            apron_sf REAL,
            curb_lf REAL,
            driveway_sf REAL,
            sidewalk_cy REAL,
            apron_cy REAL,
            curb_cy REAL,
            driveway_cy REAL,
            total_sf REAL,
            total_cy REAL,
            created_at TIMESTAMP,
            notes TEXT
        )
    """)
    conn.commit()
    return conn

# PDF extraction
class PlotPlanExtractor:
    def __init__(self):
        self.measurements = {
            'address': '',
            'block': '',
            'lot': '',
            'sidewalk_sqft': 0,
            'apron_sqft': 0,
            'curb_lf': 0,
            'driveway_sqft': 0,
        }

    def extract(self, pdf_bytes):
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            self._parse_text(text)
            return self.measurements
        except Exception as e:
            st.error(f"Error reading PDF: {e}")
            return self.measurements

    def _parse_text(self, text):
        text_upper = text.upper()

        # Extract address
        addr_pattern = r'(\d+\s+[A-Z]+\s+(?:AVENUE|AVE|STREET|ST|ROAD|RD|DRIVE|DR))'
        match = re.search(addr_pattern, text)
        if match:
            self.measurements['address'] = match.group(1)

        # Extract block/lot
        block_match = re.search(r'BLOCK\s*(\d+(?:\.\d+)?)', text_upper)
        if block_match:
            self.measurements['block'] = block_match.group(1)

        lot_match = re.search(r'LOT\s*(\d+(?:\.\d+)?)', text_upper)
        if lot_match:
            self.measurements['lot'] = lot_match.group(1)

        # Sidewalk
        sidewalk_pattern = r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:SIDEWALK|WALK)'
        matches = re.findall(sidewalk_pattern, text_upper)
        if matches:
            self.measurements['sidewalk_sqft'] = float(matches[0][0]) * float(matches[0][1])

        # Apron
        apron_pattern = r'(?:APRON)[^0-9]*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)'
        matches = re.findall(apron_pattern, text_upper)
        if matches:
            self.measurements['apron_sqft'] = float(matches[0][0]) * float(matches[0][1])

        # Curb
        curb_pattern = r'(?:CURB|D-CURB)[^0-9]*(\d+(?:\.\d+)?)'
        match = re.search(curb_pattern, text_upper)
        if match:
            self.measurements['curb_lf'] = float(match.group(1))

        # Driveway
        driveway_pattern = r'(?:DRIVEWAY)[^0-9]*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)'
        matches = re.findall(driveway_pattern, text_upper)
        if matches:
            self.measurements['driveway_sqft'] = float(matches[0][0]) * float(matches[0][1])

def calculate_volumes(sidewalk, apron, curb, driveway):
    sidewalk_cy = (sidewalk * 0.333) / 27
    apron_cy = (apron * 0.5) / 27
    curb_cy = (curb * 0.5 * 0.5) / 27
    driveway_cy = (driveway * 0.5) / 27

    total_sf = sidewalk + apron + driveway
    total_cy = sidewalk_cy + apron_cy + curb_cy + driveway_cy

    return {
        'sidewalk_cy': round(sidewalk_cy, 2),
        'apron_cy': round(apron_cy, 2),
        'curb_cy': round(curb_cy, 2),
        'driveway_cy': round(driveway_cy, 2),
        'total_sf': round(total_sf, 2),
        'total_cy': round(total_cy, 2),
    }

def save_project(conn, address, block, lot, sidewalk, apron, curb, driveway, volumes):
    c = conn.cursor()
    c.execute("""
        INSERT INTO projects 
        (address, block, lot, sidewalk_sf, apron_sf, curb_lf, driveway_sf,
         sidewalk_cy, apron_cy, curb_cy, driveway_cy, total_sf, total_cy, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        address, block, lot, sidewalk, apron, curb, driveway,
        volumes['sidewalk_cy'], volumes['apron_cy'], volumes['curb_cy'], 
        volumes['driveway_cy'], volumes['total_sf'], volumes['total_cy'],
        datetime.now()
    ))
    conn.commit()

def get_projects(conn):
    c = conn.cursor()
    c.execute("SELECT * FROM projects ORDER BY created_at DESC")
    return c.fetchall()

# Main app
st.title("📐 Plot Plan Concrete Takeoff Reader")
st.markdown("Extract measurements from plot plans and calculate concrete volumes")

# Initialize database
conn = init_db()

# Sidebar
with st.sidebar:
    st.header("Options")
    view = st.radio("View", ["Upload & Extract", "Saved Projects", "Statistics"])

# Main content
if view == "Upload & Extract":
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Upload PDF Plot Plan")
        uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

        if uploaded_file:
            st.success("PDF uploaded!")

            # Extract from PDF
            extractor = PlotPlanExtractor()
            measurements = extractor.extract(uploaded_file.getvalue())

            st.write("### Extracted Values:")
            col1a, col1b = st.columns(2)

            with col1a:
                st.metric("Sidewalk", f"{measurements['sidewalk_sqft']} SF")
                st.metric("Curb", f"{measurements['curb_lf']} LF")

            with col1b:
                st.metric("Apron", f"{measurements['apron_sqft']} SF")
                st.metric("Driveway", f"{measurements['driveway_sqft']} SF")
        else:
            st.info("Upload a PDF to get started")

    with col2:
        st.subheader("Manual Entry")
        address = st.text_input("Address")
        block = st.text_input("Block")
        lot = st.text_input("Lot")

        col2a, col2b = st.columns(2)
        with col2a:
            sidewalk = st.number_input("Sidewalk (SF)", min_value=0.0, step=1.0)
            curb = st.number_input("Curb (LF)", min_value=0.0, step=1.0)

        with col2b:
            apron = st.number_input("Apron (SF)", min_value=0.0, step=1.0)
            driveway = st.number_input("Driveway (SF)", min_value=0.0, step=1.0)

        if st.button("Calculate"):
            if address:
                volumes = calculate_volumes(sidewalk, apron, curb, driveway)

                st.success("Calculated!")
                st.json({
                    "address": address,
                    "block": block,
                    "lot": lot,
                    "sidewalk_sf": sidewalk,
                    "apron_sf": apron,
                    "curb_lf": curb,
                    "driveway_sf": driveway,
                    "volumes": volumes
                })

                if st.button("Save Project"):
                    save_project(conn, address, block, lot, sidewalk, apron, curb, driveway, volumes)
                    st.success("Project saved!")
            else:
                st.error("Please enter an address")

elif view == "Saved Projects":
    st.subheader("All Projects")
    projects = get_projects(conn)

    if projects:
        df = pd.DataFrame(projects, columns=[
            'ID', 'Address', 'Block', 'Lot', 'Sidewalk SF', 'Apron SF', 
            'Curb LF', 'Driveway SF', 'Sidewalk CY', 'Apron CY', 
            'Curb CY', 'Driveway CY', 'Total SF', 'Total CY', 'Date', 'Notes'
        ])

        st.dataframe(df, use_container_width=True)

        # Export button
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name=f"projects_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No projects saved yet")

elif view == "Statistics":
    st.subheader("Project Statistics")
    projects = get_projects(conn)

    if projects:
        df = pd.DataFrame(projects, columns=[
            'ID', 'Address', 'Block', 'Lot', 'Sidewalk SF', 'Apron SF', 
            'Curb LF', 'Driveway SF', 'Sidewalk CY', 'Apron CY', 
            'Curb CY', 'Driveway CY', 'Total SF', 'Total CY', 'Date', 'Notes'
        ])

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Projects", len(df))
        with col2:
            st.metric("Avg Total CY", f"{df['Total CY'].mean():.2f}")
        with col3:
            st.metric("Total Concrete", f"{df['Total CY'].sum():.2f} CY")
        with col4:
            st.metric("Avg Total SF", f"{df['Total SF'].mean():.2f}")

        st.bar_chart(df.set_index('Address')['Total CY'])
    else:
        st.info("No statistics available yet")

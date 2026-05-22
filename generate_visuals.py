"""
generate_visuals.py
--------------------
Pulls data from ai_job_market PostgreSQL database and generates
all charts and maps used in the weekly AI Job Market report.

Outputs saved to: outputs/visuals/

Usage:
    python generate_visuals.py

Requirements:
    pip install psycopg2-binary pandas matplotlib seaborn plotly python-dotenv kaleido
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import plotly.express as px
import plotly.io as pio
import psycopg2
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "ai_job_market"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

OUTPUT_DIR = "outputs/visuals"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Colorblind-friendly Seaborn palette ───────────────────────────────────────
PALETTE     = sns.color_palette("colorblind")
ACCENT      = "#1F4E79"   # dark navy for titles/accents
POS_COLOR   = "#2196F3"   # blue  for positive % change
NEG_COLOR   = "#E53935"   # red   for negative % change
BG_COLOR    = "#F8F9FA"   # light grey background
GRID_COLOR  = "#DDDDDD"

TITLE_FONT  = {"fontsize": 14, "fontweight": "bold", "color": ACCENT, "pad": 14}
LABEL_FONT  = {"fontsize": 12, "color": "#333333"}
TICK_FONT   = 12
FIG_DPI     = 150


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query(sql: str, params=None) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def two_latest_dates(table: str, date_col: str = "date") -> tuple:
    """Return the two most recent dates in a table."""
    df = query(f'SELECT DISTINCT "{date_col}" FROM "{table}" ORDER BY "{date_col}" DESC LIMIT 2')
    dates = df[date_col].tolist()
    if len(dates) < 2:
        raise ValueError(f"Not enough dates in {table} to calculate % change.")
    return dates[0], dates[1]   # latest, previous


def pct_change(new_val, old_val) -> float:
    if old_val == 0 or pd.isna(old_val):
        return 0.0
    return round((new_val - old_val) / old_val * 100, 2)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def style_ax(ax, title: str, xlabel: str = "", ylabel: str = ""):
    #ax.set_facecolor(BG_COLOR)
    ax.set_facecolor("none")
    ax.set_title(title, **TITLE_FONT)
    if xlabel:
        ax.set_xlabel(xlabel, **LABEL_FONT)
    if ylabel:
        ax.set_ylabel(ylabel, **LABEL_FONT)
    ax.tick_params(labelsize=TICK_FONT)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)


def save_fig(fig, filename: str, transparent: bool = False):
    path = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight",
                #facecolor="white", edgecolor="none")
                facecolor="none" if transparent else "white", 
                edgecolor="none",
                transparent=transparent)
    plt.close(fig)
    print(f"   ✓ Saved: {filename}")


# ── Chart 1: Global Job Trends (line chart) ───────────────────────────────────

DATE_FROM = "2025-09-01"
DATE_TO = None

def chart_global_trends():
    where = ""
    params = []
    if DATE_FROM:
        where += 'AND date >= %s'
        params.append(DATE_FROM)
    if DATE_TO:
        where += 'AND date <= %s'
        params.append(DATE_TO)  

    df = query(f'SELECT date, worldwide AS total_jobs FROM global_jobs_ai WHERE 1=1 {where} ORDER BY date',
               params if params else None
               )
    df["date"] = pd.to_datetime(df["date"])

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")

    # Main line
    ax.plot(df["date"], df["total_jobs"], marker="o", color=ACCENT,
            linewidth=2.5, markersize=5, label="Worldwide AI Jobs")

    # Trendline
    x = np.arange(len(df))
    y = df["total_jobs"]
    trendline = np.poly1d(np.polyfit(x, y, 1))
    ax.plot(df["date"], trendline(x), linestyle="dotted", color=NEG_COLOR,
            linewidth=2, label="Trend")

    style_ax(ax, "Global AI Job Openings Over Time (Worldwide)",
             xlabel="Date", ylabel="Job Openings")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b '%y"))
    ax.tick_params(axis="x", rotation=45)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.legend(fontsize=10, framealpha=0.7)

    fig.tight_layout()
    save_fig(fig, "01_global_trends.png", transparent=True)

# ── Chart 2: AI Jobs by country ───────────────────────────────
def chart_jobs_by_country():
    latest = query(
        'SELECT DISTINCT date FROM global_jobs_ai ORDER BY date DESC LIMIT 1'
    )["date"].values[0]

    df_row = query('SELECT * FROM global_jobs_ai WHERE date = %s', (latest,))
    df_row = df_row.drop(columns=["date", "worldwide"])

    # Melt wide → long and sort low to high
    df = df_row.melt(var_name="country", value_name="job_count")
    df["job_count"] = pd.to_numeric(df["job_count"], errors="coerce").fillna(0).astype(int)
    df["country"] = df["country"].str.replace("_", " ").str.upper()
    df = df.sort_values("job_count", ascending=True)

    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")

    bars = ax.bar(df["country"], df["job_count"], color=ACCENT, edgecolor="none", width=0.6)

    # Job count label on each bar
    for bar, val in zip(bars, df["job_count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 300,
            f"{val:,}",
            ha="center", va="bottom",
            fontsize=10, color="#333333", rotation=90
        )

    style_ax(ax, f'"AI" Focused Roles by Country — {latest}', ylabel="Job Openings")
    ax.set_xticklabels(df["country"], rotation=90, ha="center", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="x", visible=False)

    fig.tight_layout()
    save_fig(fig, "02_jobs_by_country.png", transparent=True)

# ── Chart 3: Remote / Hybrid / Onsite Over Time ───────────────────────────────

def chart_remote_hybrid_onsite():
    df = query('SELECT * FROM job_site_ai ORDER BY date')
    df["date"] = pd.to_datetime(df["date"])

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("white")

    colors = sns.color_palette("colorblind", 3)
    for col, color, label in zip(
        ["remote", "hybrid", "onsite"],
        colors,
        ["Remote", "Hybrid", "On-Site"]
    ):
        ax.plot(df["date"], df[col], label=label, color=color,
                linewidth=2.5, marker="o", markersize=4)
        ax.fill_between(df["date"], df[col], alpha=0.08, color=color)

    style_ax(ax, "Remote / Hybrid / On-Site Roles Over Time", ylabel="Open Roles")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b '%y"))
    ax.tick_params(axis="x", rotation=30)
    ax.legend(fontsize=10, framealpha=0.7)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

    fig.tight_layout()
    save_fig(fig, "03_remote_hybrid_onsite.png", transparent=True)


# ── Chart 4: Industry % Change (horizontal bar) ───────────────────────────────

def chart_industry_change():
    latest, previous = two_latest_dates("industry_jobs_ai")

    df_new = query('SELECT * FROM industry_jobs_ai WHERE date = %s', (latest,))
    df_old = query('SELECT * FROM industry_jobs_ai WHERE date = %s', (previous,))

    exclude = {"date"}
    cols = [c for c in df_new.columns if c not in exclude]

    records = []
    for col in cols:
        new_val = df_new[col].values[0] if not df_new.empty else 0
        old_val = df_old[col].values[0] if not df_old.empty else 0
        records.append({
            "industry": col.replace("_", " ").title(),
            "pct_change": pct_change(new_val, old_val),
            "current": new_val
        })

    df = pd.DataFrame(records).sort_values("pct_change", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")

    colors = [POS_COLOR if x >= 0 else NEG_COLOR for x in df["pct_change"]]
    bars = ax.barh(df["industry"], df["pct_change"], color=colors, edgecolor="none", height=0.6)

    # Add value labels
    for bar, val in zip(bars, df["pct_change"]):
        x_pos = bar.get_width() + (0.5 if val >= 0 else -0.5)
        ha = "left" if val >= 0 else "right"
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center", ha=ha, fontsize=10, color="#333333")

    ax.axvline(0, color="#333333", linewidth=0.8)
    style_ax(ax, f"AI Jobs by Industry — % Change\n{previous} → {latest}",
             xlabel="% Change")
    ax.tick_params(labelsize=10)

    fig.tight_layout()
    save_fig(fig, "04_industry_change.png", transparent=True)

# ── Chart 5 and 6: Tech and Non Tech Industry charts ──────────────────────────────

def chart_industry_by_tech():
    latest = query(
        'SELECT DISTINCT date FROM industry_jobs_ai ORDER BY date DESC LIMIT 1'
    )["date"].values[0]

    df = query('SELECT * FROM industry_jobs_ai WHERE date = %s', (latest,))
    df = df.drop(columns=["date"])

    # Define Tech vs Non-Tech split
    tech_industries = [
        "appliances_electrical_and_electronics_manufacturing",
        "telecommunications",
        "semiconductor_manufacturing",
        "computer_hardware_manufacturing",
        "information_services",
        "tech_information_and_internet",
        "business_consulting_and_services",
        "tech_information_and_media",
        "it_services_and_it_consulting",
        "software_development"
    ]

    non_tech_industries = [
        "chemical_manufacturing",
        "defense_and_space_manufacturing",
        "biotechnology_research",
        "motor_vehicle_manufacturing",
        "retail",
        "insurance",
        "hospitals_and_health_care",
        "accounting",
        "pharmaceutical_manufacturing",
        "human_resources_services",
        "staffing_and_recruiting",
        "financial_services"
    ]

    def make_chart(industry_list, title, filename):
        # Build dataframe for this group
        records = []
        for col in industry_list:
            if col in df.columns:
                records.append({
                    "industry": col.replace("_", " ").title(),
                    "job_count": int(df[col].values[0]) if pd.notna(df[col].values[0]) else 0
                })

        df_plot = pd.DataFrame(records).sort_values("job_count", ascending=True)

        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor("none")
        ax.set_facecolor("none")

        bars = ax.bar(df_plot["industry"], df_plot["job_count"],
                      color=ACCENT, edgecolor="none", width=0.6)

        # Job count label above each bar
        for bar, val in zip(bars, df_plot["job_count"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 50,
                f"{val:,}",
                ha="center", va="bottom", fontsize=11, color="#333333"
            )

        ax.set_title(f"{title}\n{latest.strftime('%m.%d.%Y') if hasattr(latest, 'strftime') else latest}",
                     fontsize=13, fontweight="bold", color=ACCENT, pad=12)
        ax.set_ylabel("Job Openings", fontsize=10, color="#333333")
        ax.set_xticklabels(df_plot["industry"], rotation=30, ha="right", fontsize=10)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        fig.tight_layout()
        save_fig(fig, filename, transparent=True)

    make_chart(tech_industries,     "TECH INDUSTRIES",     "05_tech_industries.png")
    make_chart(non_tech_industries, "NON-TECH INDUSTRIES", "06_non_tech_industries.png")


# ── Chart 7: Role Type % Change (horizontal bar) ──────────────────────────────

def chart_role_type_change():
    latest, previous = two_latest_dates("role_type_ai")

    df_new = query('SELECT * FROM role_type_ai WHERE date = %s', (latest,))
    df_old = query('SELECT * FROM role_type_ai WHERE date = %s', (previous,))

    exclude = {"date"}
    cols = [c for c in df_new.columns if c not in exclude]

    records = []
    for col in cols:
        new_val = df_new[col].values[0] if not df_new.empty else 0
        old_val = df_old[col].values[0] if not df_old.empty else 0
        records.append({
            "role": col.replace("_", " ").title(),
            "pct_change": pct_change(new_val, old_val),
            "current": new_val
        })

    df = pd.DataFrame(records).sort_values("pct_change", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")

    colors = [POS_COLOR if x >= 0 else NEG_COLOR for x in df["pct_change"]]
    bars = ax.barh(df["role"], df["pct_change"], color=colors, edgecolor="none", height=0.6)

    for bar, val in zip(bars, df["pct_change"]):
        x_pos = bar.get_width() + (0.5 if val >= 0 else -0.5)
        ha = "left" if val >= 0 else "right"
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center", ha=ha, fontsize=11, color="#333333")

    ax.axvline(0, color="#333333", linewidth=0.8)
    style_ax(ax, f"AI Role Types — % Change\n{previous} → {latest}",
             xlabel="% Change")
    ax.tick_params(labelsize=11)

    fig.tight_layout()
    save_fig(fig, "07_role_type_change.png", transparent=True)

# ----------Chart 8: Roles by Count ------------------------
def chart_roles_by_count():
    latest = query(
        'SELECT DISTINCT date FROM role_type_ai ORDER BY date DESC LIMIT 1'
    )["date"].values[0]

    df = query('SELECT * FROM role_type_ai WHERE date = %s', (latest,))
    df = df.drop(columns=["date"])

    # Melt wide → long and sort high to low
    records = []
    for col in df.columns:
        records.append({
            "role": col.replace("_", " ").title(),
            "job_count": int(df[col].values[0]) if pd.notna(df[col].values[0]) else 0
        })

    df_plot = pd.DataFrame(records).sort_values("job_count", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")

    bars = ax.barh(df_plot["role"], df_plot["job_count"],
                   color=ACCENT, edgecolor="none", height=0.6)

    # Job count label at end of each bar
    for bar, val in zip(bars, df_plot["job_count"]):
        ax.text(
            bar.get_width() + 50,
            bar.get_y() + bar.get_height() / 2,
            f"{val:,}",
            va="center", ha="left", fontsize=10, color="#333333"
        )

    date_label = latest.strftime('%m.%d.%Y') if hasattr(latest, 'strftime') else latest
    ax.set_title(f'"AI" Focused Roles\n{date_label}',
                 fontsize=14, fontweight="bold", color=ACCENT, pad=12)
    ax.set_xlabel("Job Openings", fontsize=11, color="#333333")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.7, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=10)

    fig.tight_layout()
    save_fig(fig, "08_roles_by_count.png", transparent=True)

# ── Chart 9: Company table ───────────────────────────────────────
def chart_company_table(date_from=None, date_to=None):
    # Get two most recent dates if not specified
    if date_from is None or date_to is None:
        latest, previous = two_latest_dates("company_jobs_ai")
        date_to   = date_to   or latest
        date_from = date_from or previous

    df_new = query(
        'SELECT company, industry, job_count FROM company_jobs_ai WHERE date = %s',
        (date_to,)
    )
    df_old = query(
        'SELECT company, job_count FROM company_jobs_ai WHERE date = %s',
        (date_from,)
    )

    df = df_new.merge(df_old, on="company", suffixes=("_new", "_old"))
    df["delta"] = df.apply(
        lambda r: pct_change(r["job_count_new"], r["job_count_old"]), axis=1
    )
    df["delta_label"] = df["delta"].apply(lambda x: f"{x:+.0f}%")
    df = df.sort_values("company")

    # Format date labels for column headers
    d1 = pd.to_datetime(date_from).strftime("%m.%d.%Y")
    d2 = pd.to_datetime(date_to).strftime("%m.%d.%Y")

    # Build figure
    fig, ax = plt.subplots(figsize=(14, len(df) * 0.40 + 2.5))
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")
    ax.axis("off")

    # Table data
    col_labels = ["Company", "Industry", d1, d2, "Delta"]
    table_data = [
        [
            row["company"],
            row["industry"],
            f"{int(row['job_count_old']):,}",
            f"{int(row['job_count_new']):,}",
            row["delta_label"]
        ]
        for _, row in df.iterrows()
    ]

    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        loc="center",
        cellLoc="left"
    )

    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.scale(1, 1.6)

    # Style header row
    for col_idx in range(len(col_labels)):
        cell = table[0, col_idx]
        cell.set_facecolor(ACCENT)
        cell.set_text_props(color="white", fontweight="bold")

    # Style data rows — alternating background + delta color coding
    for row_idx, (_, row) in enumerate(df.iterrows(), start=1):
        bg = "#EEF4FB" if row_idx % 2 == 0 else "white"
        for col_idx in range(len(col_labels)):
            cell = table[row_idx, col_idx]
            cell.set_facecolor(bg)
            cell.set_edgecolor("#DDDDDD")

        # Color delta cell
        delta_cell = table[row_idx, 4]
        if row["delta"] > 0:
            delta_cell.set_text_props(color="#2E7D32", fontweight="bold")  # green
        elif row["delta"] < 0:
            delta_cell.set_text_props(color="#C62828", fontweight="bold")  # red
        else:
            delta_cell.set_text_props(color="#333333")

    # Column widths
    table.auto_set_column_width([0, 1, 2, 3, 4])

  
    fig.tight_layout()

    # Position title just above the table using figure-level text
    fig.text(
        0.5, 0.91,
        f'"AI" Job Openings by Company\n{d1}  →  {d2}',
        ha="center", va="top",
        fontsize=20, fontweight="bold", color=ACCENT,
        linespacing=1.5
    )

    save_fig(fig, "09_company_table.png", transparent=True)


   


# ── Chart 10: US State Map (Plotly choropleth) ─────────────────────────────────

def chart_us_state_map():
    latest = query(
        'SELECT DISTINCT date FROM us_states_ai ORDER BY date DESC LIMIT 1'
    )["date"].values[0]
 
    df_row = query('SELECT * FROM us_states_ai WHERE date = %s', (latest,))
    df_row = df_row.drop(columns=["date"])
 
    # Melt wide → long: state_name | job_count
    df = df_row.melt(var_name="state_name", value_name="job_count")
    df["job_count"] = pd.to_numeric(df["job_count"], errors="coerce").fillna(0).astype(int)
 
    # State name → abbreviation mapping
    state_abbrev = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
        "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
        "nevada": "NV", "new_hampshire": "NH", "new_jersey": "NJ",
        "new_mexico": "NM", "new_york": "NY", "north_carolina": "NC",
        "north_dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
        "pennsylvania": "PA", "rhode_island": "RI", "south_carolina": "SC",
        "south_dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA",
        "west_virginia": "WV", "wisconsin": "WI", "wyoming": "WY"
    }
 
    df["state"] = df["state_name"].map(state_abbrev)
    df["state_label"] = df["state_name"].str.replace("_", " ").str.title()
    df = df.dropna(subset=["state"])
 
    # Only show label for states above threshold to avoid crowding small states
    df["label"] = df["job_count"].apply(lambda x: f"{x:,}" if x >= 0 else "")
 
    fig = px.choropleth(
        df,
        locations="state",
        locationmode="USA-states",
        color="job_count",
        scope="usa",
        color_continuous_scale="Blues",
        hover_name="state_label",
        hover_data={"job_count": ":,", "state": False},
        labels={"job_count": "Open Roles"},
        title=f'"AI" Job Openings by US State — {latest}',
    )
 
   # Add state labels as a separate scatter layer
    import plotly.graph_objects as go
    # Determine font color per state: white for dark fills, black for light fills
    max_val = df["job_count"].max()
    threshold = max_val * 0.5  # states above 50% of max get white text

    df_labels = df[df["label"] != ""].copy()
    df_labels["font_color"] = df_labels["job_count"].apply(
        lambda x: "white" if x >= threshold else "black"
    )

    # Add one trace per color group
    for color, group in df_labels.groupby("font_color"):
        fig.add_trace(go.Scattergeo(
            locations=group["state"],
            locationmode="USA-states",
            text=group["label"],
            mode="text",
            textfont=dict(size=8, color=color),
            hoverinfo="skip",
            showlegend=False
        ))

  
    fig.update_layout(
        title_font=dict(size=14, color=ACCENT),
        title_x=0.5,
        geo=dict(bgcolor="rgba(0,0,0,0)", lakecolor="white"),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=50, b=0),
        coloraxis_colorbar=dict(title="Open Roles"),
    )
 
    # Save as interactive HTML
    html_path = os.path.join(OUTPUT_DIR, "10_us_state_map.html")
    fig.write_html(html_path)
    print(f"   ✓ Saved: 10_us_state_map.html")
 
    # Save as static PNG for PowerPoint
    try:
        png_path = os.path.join(OUTPUT_DIR, "10_us_state_map.png")
        fig.write_image(png_path, width=1200, height=650, scale=2)
        print(f"   ✓ Saved: 10_us_state_map.png")
    except Exception as e:
        print(f"   ⚠ PNG export failed (kaleido may not be installed): {e}")
        print(f"     Run: pip install kaleido")


# ── Charts 11 - 13: Regional Maps (Americas, Europe, APAC/Middle East) ─────────────────────────

# db_column → ISO-3 code (used by Plotly for reliable country matching)
REGION_COUNTRIES = {
    "americas": {
        "united_states": "USA",
        "canada":        "CAN",
        "mexico":        "MEX",
        "colombia":      "COL",
        "argentina":     "ARG",
        "brazil":        "BRA",
        "uruguay":       "URY",
    },
    "europe": {
        "united_kingdom": "GBR",
        "germany":        "DEU",
        "france":         "FRA",
        "spain":          "ESP",
        "portugal":       "PRT",
        "italy":          "ITA",
        "ireland":        "IRL",
        "poland":         "POL",
        "netherlands":    "NLD",
        "belgium":        "BEL",
        "norway":         "NOR",
        "finland":        "FIN",
        "sweden":         "SWE",
        "austria":        "AUT",
        "czech_republic": "CZE",
        "south_africa":   "ZAF",
    },
    "apac": {
        "india":        "IND",
        "china":        "CHN",
        "japan":        "JPN",
        "singapore":    "SGP",
        "south_korea":  "KOR",
        "australia":    "AUS",
        "new_zealand":  "NZL",
        "israel":       "ISR",
        "uae":          "ARE",
        "saudi_arabia": "SAU",
    }
}
 
REGION_SCOPE = {
    "americas": {"scope": "world", "lataxis_range": [-58, 72], "lonaxis_range": [-168, -25]},
    "europe":   {"scope": "europe", "projection_scale": 1.7},
    "apac":     {"scope": "world", "center": {"lat": 20, "lon": 110}, "projection_scale": 1.3},
}
 
REGION_TITLES = {
    "americas": "Americas — AI Job Openings by Country",
    "europe":   "Europe — AI Job Openings by Country",
    "apac":     "APAC & Middle East — AI Job Openings by Country",
}
 
REGION_FILENAMES = {
    "americas": "11_americas_map",
    "europe":   "12_europe_map",
    "apac":     "13_apac_map",
}
# ISO-3 → display name for labels
ISO3_NAMES = {
    "USA": "United States", "CAN": "Canada", "MEX": "Mexico",
    "COL": "Colombia", "ARG": "Argentina", "BRA": "Brazil", "URY": "Uruguay",
    "GBR": "United Kingdom", "DEU": "Germany", "FRA": "France", "ESP": "Spain",
    "PRT": "Portugal", "ITA": "Italy", "IRL": "Ireland", "POL": "Poland",
    "NLD": "Netherlands", "BEL": "Belgium", "NOR": "Norway", "FIN": "Finland",
    "SWE": "Sweden", "AUT": "Austria", "CZE": "Czech Republic", "ZAF": "South Africa",
    "IND": "India", "CHN": "China", "JPN": "Japan", "SGP": "Singapore",
    "KOR": "South Korea", "AUS": "Australia", "NZL": "New Zealand",
    "ISR": "Israel", "ARE": "UAE", "SAU": "Saudi Arabia",
}
 
 
 
 
def chart_regional_map(region: str):
    latest = query(
        'SELECT DISTINCT date FROM global_jobs_ai ORDER BY date DESC LIMIT 1'
    )["date"].values[0]
 
    df_row = query('SELECT * FROM global_jobs_ai WHERE date = %s', (latest,))
 
    # Build long format for this region only
    country_map = REGION_COUNTRIES[region]
    records = []
    for db_col, iso3 in country_map.items():
        if db_col in df_row.columns:
            val = df_row[db_col].values[0]
            job_count = int(val) if pd.notna(val) else 0
            records.append({
                "country":      iso3,                          # ISO-3 code for Plotly
                "country_name": ISO3_NAMES.get(iso3, iso3),   # display name for hover
                "job_count":    job_count,
                "label":        f"{job_count:,}" if job_count >= 100 else ""
            })
 
    df = pd.DataFrame(records)
 
    # Build choropleth
    scope_args = REGION_SCOPE[region]
    date_label = pd.to_datetime(str(latest)).strftime("%m.%d.%Y")
 
     
    fig = px.choropleth(
        df,
        locations="country",
        locationmode="ISO-3",
        color="job_count",
        color_continuous_scale="Blues",
        hover_name="country_name",
        hover_data={"job_count": ":,", "country": False, "country_name": False},
        labels={"job_count": "Open Roles"},
        title=f"{REGION_TITLES[region]} — {date_label}",
    )
 
    # Apply region-specific scope
    geo_settings = dict(
        bgcolor="white",
        lakecolor="white",
        showland=True,
        landcolor="#F0F0F0",
        showocean=True,
        oceancolor="#EAF4FB",
        showcountries=True,
        countrycolor="#CCCCCC",
        scope=scope_args.get("scope", "world"),
    )
    if "center" in scope_args:
        geo_settings["center"] = scope_args["center"]
    if "projection_scale" in scope_args:
        geo_settings["projection_scale"] = scope_args["projection_scale"]
    if "lataxis_range" in scope_args:
        geo_settings["lataxis_range"] = scope_args["lataxis_range"]
    if "lonaxis_range" in scope_args:
        geo_settings["lonaxis_range"] = scope_args["lonaxis_range"]
 
    fig.update_geos(**geo_settings)
 
    # Add country labels as scatter layer
    import plotly.graph_objects as go
    df_labels = df[df["label"] != ""]
    fig.add_trace(go.Scattergeo(
        locations=df_labels["country"],
        locationmode="ISO-3",
        text=df_labels["label"],
        mode="text",
        textfont=dict(size=9, color="black"),
        hoverinfo="skip",
        showlegend=False
    ))
 
    fig.update_layout(
        title_font=dict(size=14, color=ACCENT),
        paper_bgcolor="white",
        margin=dict(l=0, r=0, t=50, b=0),
        coloraxis_colorbar=dict(title="Open Roles"),
    )
 
    filename = REGION_FILENAMES[region]
 
    # Save HTML
    fig.write_html(os.path.join(OUTPUT_DIR, f"{filename}.html"))
    print(f"   ✓ Saved: {filename}.html")
 
    # Save PNG
    try:
        fig.write_image(os.path.join(OUTPUT_DIR, f"{filename}.png"),
                        width=1200, height=700, scale=2)
        print(f"   ✓ Saved: {filename}.png")
    except Exception as e:
        print(f"   ⚠ PNG export failed: {e}")
 
 
def chart_americas_map():
    chart_regional_map("americas")
 
def chart_europe_map():
    chart_regional_map("europe")
 
def chart_apac_map():
    chart_regional_map("apac")
 

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  AI Job Market — Visualization Generator")
    print("=" * 60)

    charts = [
        ("Global job trends",           chart_global_trends),
        ("Jobs by country",              chart_jobs_by_country),
        ("Remote/Hybrid/Onsite trends", chart_remote_hybrid_onsite),
        ("Industry % change",           chart_industry_change),
        ("Tech industries",             chart_industry_by_tech),
        ("Non-Tech industries",         chart_industry_by_tech),
        ("Role type % change",          chart_role_type_change),
        ("AI roles by count",            chart_roles_by_count),
        ("Company Table",               chart_company_table),
        ("US state map",                chart_us_state_map),
        ("Americas map",         chart_americas_map),
        ("Europe map",           chart_europe_map),
        ("APAC/Middle East map", chart_apac_map),   
    ]

    errors = []
    for name, fn in charts:
        print(f"\n→ Generating: {name} ...")
        try:
            fn()
        except Exception as e:
            print(f"   ✗ FAILED: {e}")
            errors.append((name, str(e)))

    print(f"\n{'=' * 60}")
    print(f"  Done. Visuals saved to: {OUTPUT_DIR}/")
    if errors:
        print(f"\n  ⚠ {len(errors)} chart(s) failed:")
        for name, msg in errors:
            print(f"     • {name}: {msg}")
    print("=" * 60)


if __name__ == "__main__":
    main()
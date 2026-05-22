# AI Job Market Tracker

A end-to-end data pipeline that aggregates AI-focused job openings from LinkedIn, loads them into a PostgreSQL database, generates visualizations, builds a PowerPoint report, and uses an AI agent to surface week-over-week insights — all from a single local Python environment.

---

## Overview

This project automates a recurring AI job market analysis workflow. Raw job opening data is collected weekly from LinkedIn and processed through a four-stage pipeline:

```
Excel (LinkedIn data)
        ↓
etl_excel_to_postgres.py     — loads data into PostgreSQL
        ↓
generate_visuals.py          — generates charts and maps
        ↓
generate_pptx.py             — assembles PowerPoint deck
        ↓
agent.py                     — AI-powered week-over-week analysis
```

The output is a draft PowerPoint report with embedded visuals and AI-generated insights, used to inform a recurring LinkedIn post on the state of AI hiring.

---

## What It Tracks

Data is aggregated weekly across eight dimensions:

| Dimension | Description |
|---|---|
| Global job openings | Total worldwide AI roles + 23 individual countries |
| US state openings | AI roles across all 50 US states |
| Industry breakdown | AI hiring across 20 industry verticals (tech and non-tech) |
| Role types | 23 specific AI role titles (e.g. ML Engineer, LLM Engineer, AI Product Manager) |
| Company openings | 30 selected companies tracked individually |
| Work location | Remote / hybrid / on-site split |
| Global employers | Company-level hiring by country |
| US state employers | Company-level hiring by US state |

---

## Project Structure

```
EXCEL_TO_POSTGRE/
├── .env                          # Credentials (not committed)
├── .gitignore
├── data/
│   └── CAIO list clean.xlsx      # Source data (LinkedIn aggregation)
├── outputs/
│   ├── visuals/                  # Generated chart and map PNGs
│   └── AI_Job_Market_Report_YYYYMMDD.pptx
├── etl_excel_to_postgres.py      # Stage 1: Excel → PostgreSQL
├── generate_visuals.py           # Stage 2: PostgreSQL → charts/maps
├── generate_pptx.py              # Stage 3: Visuals → PowerPoint
├── agent.py                      # Stage 4: AI analytics agent
├── db.py                         # Shared DB connection module
├── schema_context.md             # Agent system prompt / schema reference
└── requirements.txt
```

---

## Pipeline Stages

### Stage 1 — ETL: Excel → PostgreSQL (`etl_excel_to_postgres.py`)

Reads all eight sheets from the Excel source file and upserts them into the `ai_job_market` PostgreSQL database. Uses `INSERT ... ON CONFLICT DO UPDATE` logic so re-running the script is safe — existing rows are updated, not duplicated.

**Key behaviors:**
- Column names are normalized to safe SQL identifiers
- Dates are coerced to `DATE` type; rows with unparseable dates are dropped
- The `company_jobs_ai` sheet has a two-row header (company name + industry) and is melted from wide to long format automatically
- All sheets support partial updates — only changed values are overwritten

**Run:**
```bash
python etl_excel_to_postgres.py
```

---

### Stage 2 — Visualizations (`generate_visuals.py`)

Queries the PostgreSQL database and generates 13 charts and maps saved to `outputs/visuals/`.

| File | Chart |
|---|---|
| `01_global_trends.png` | Worldwide AI job openings over time (line + trendline) |
| `02_jobs_by_country.png` | AI roles by country, current week (bar chart) |
| `03_remote_hybrid_onsite.png` | Remote / hybrid / on-site trend over time |
| `04_industry_change.png` | Industry % change week-over-week (horizontal bar) |
| `05_tech_industries.png` | Tech industry job counts, current week |
| `06_non_tech_industries.png` | Non-tech industry job counts, current week |
| `07_role_type_change.png` | AI role type % change week-over-week |
| `08_roles_by_count.png` | AI role counts by title, current week |
| `09_company_table.png` | Company job counts with delta, two-period comparison |
| `10_us_state_map.png` | US choropleth map of AI role openings by state |
| `11_americas_map.png` | Americas regional choropleth map (test map/formatting needs work) | 
| `12_europe_map.png` | Europe regional choropleth map (test map/formatting needs work)|
| `13_apac_map.png` | APAC and Middle East regional choropleth map (test map/formatting needs work) | 

All charts use a colorblind-friendly Seaborn palette. Maps are generated as both interactive HTML and static PNG (for PowerPoint embedding).

**Run:**
```bash
python generate_visuals.py
```

---

### Stage 3 — PowerPoint Builder (`generate_pptx.py`)

Takes the PNG visuals from Stage 2 and assembles them into a PowerPoint deck by modifying a reference template (`ppt_template.pptx`). Embedded charts and tables from the template are removed and replaced with the freshly generated visuals.

**Before running**, update the two date constants at the top of the file:
```python
REPORT_DATE = "05.19.2026"   # current report date (MM.DD.YYYY)
PREV_DATE   = "05.04.2026"   # previous report date (MM.DD.YYYY)
```

**Slide map:**

| Slide | Content |
|---|---|
| 1 | Cover — report date updated automatically |
| 2 | Methodology — static, no changes |
| 3 | Global trends (line chart + remote/hybrid/onsite) |
| 4 | Country bar chart + remote trend |
| 5 | Industry breakdown (tech, non-tech, % change) |
| 6 | AI role types (count + % change) |
| 7 | Keyword reference — static |
| 8 | Company openings table |
| 9 | US state map |
| 10–12 | Regional maps (Americas, Europe, APAC) — appended as new slides |

Output saved to: `outputs/AI_Job_Market_Report_YYYYMMDD.pptx`

**Run:**
```bash
python generate_pptx.py
```

---

### Stage 4 — AI Analytics Agent (`agent.py`)

An AI agent powered by the Anthropic API (Claude Sonnet) that accepts natural language questions about the job market data, generates and executes PostgreSQL queries, and returns plain-English insights formatted for PowerPoint bullets.

**Pipeline:**
```
Natural language question
        ↓
Claude generates SQL (using schema_context.md as system prompt)
        ↓
Query executed against PostgreSQL (read-only)
        ↓
Results returned to Claude
        ↓
2–3 sentence insight, ready for PowerPoint or LinkedIn
```

**Safety:** The agent uses a read-only database connection and blocks any query that does not begin with `SELECT`.

**Run (interactive CLI):**
```bash
python agent.py
```

**Example questions:**
- *"Which industries had the most AI job openings this week?"*
- *"Which role types grew the most week-over-week?"*
- *"Which companies reduced their AI headcount the most this period?"*
- *"What are the top 5 US states for AI hiring right now?"*

Type `verbose` during a session to see the generated SQL alongside each insight. Type `quit` to exit.

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally
- An Anthropic API key ([get one here](https://console.anthropic.com))

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/EXCEL_TO_POSTGRE.git
cd EXCEL_TO_POSTGRE

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.template` to `.env` and fill in your values:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here

DB_HOST=localhost
DB_PORT=5432
DB_NAME=ai_job_market
DB_USER=your_postgres_username
DB_PASSWORD=your_postgres_password

EXCEL_PATH=data/CAIO list clean.xlsx
```

**Never commit `.env` to GitHub.** It is listed in `.gitignore`.

### Database

Create the `ai_job_market` database in PostgreSQL before running the ETL:

```sql
CREATE DATABASE ai_job_market;
```

All tables are created and managed by the ETL script. No manual schema setup required.

---

## Dependencies

```
anthropic>=0.25.0
psycopg2-binary>=2.9.9
python-dotenv>=1.0.0
pandas>=2.0.0
openpyxl>=3.1.0
matplotlib>=3.7.0
seaborn>=0.13.0
plotly>=5.18.0
kaleido>=0.2.1
numpy>=1.24.0
python-pptx>=0.6.21
```

---

## Running the Full Pipeline

```bash
# Stage 1: Load data
python etl_excel_to_postgres.py

# Stage 2: Generate visuals
python generate_visuals.py

# Stage 3: Build PowerPoint
python generate_pptx.py

# Stage 4: Run AI analysis
python agent.py
```

Stages 1–3 are non-interactive and run to completion. Stage 4 launches an interactive CLI session.

---

## Roadmap

- **Phase 2 — Web Research Agent:** A second agent layer that takes significant week-over-week findings (e.g. a company's roles up 20%, a country's openings spiking) and automatically searches for news, earnings announcements, and policy developments that may explain the movement.
- **Phase 3 — Public Streamlit Dashboard:** A public-facing dashboard hosted via Supabase, with filters by industry, state, company, and role type.

---

## License

MIT License. See `LICENSE` for details.

---

*Data source: LinkedIn job postings, aggregated weekly. This project is independent and not affiliated with LinkedIn.*

"""
ETL Script: CAIO_list_clean.xlsx → PostgreSQL (ai_job_market)
--------------------------------------------------------------
Handles all 8 sheets with upsert logic (INSERT ... ON CONFLICT DO UPDATE).
Run from VS Code terminal:  python etl_caio_to_postgres.py
 
Requirements:
    pip install psycopg2-binary openpyxl pandas python-dotenv
 
Credentials: set in a .env file in the same folder as this script:
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=ai_job_market
    DB_USER=your_username
    DB_PASSWORD=your_password
    EXCEL_PATH=C:/path/to/CAIO list clean.xlsx
"""
 
import os
import re
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

#-----Config-----------------------------------------------------------------------
load_dotenv()  # Load environment variables from .env file

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "ai_job_market"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"), 
    }

EXCEL_PATH = os.getenv("EXCEL_PATH", "data/CAIO list clean.xlsx")


#------Helper Functions----------------------------------------------------------------

def clean_col(name:str) -> str:
    """Normalize a column name to a safe SQL identifier."""
    name = str(name).strip()
    name = name.replace("\xa0", " ")  # Replace spaces with underscores
    name = re.sub(r"[^\w\s]", "", name)  #remove punctuation
    name = re.sub(r"\s+", "_", name)  # Replace remaining spaces with underscores
    return name.lower() 


def upsert(cur, table: str, df: pd.DataFrame, conflict_cols: list[str]) -> int:
    """
    Generic upsert: INSERT ... ON CONFLICT (conflict_cols) DO UPDATE SET ...
    Returns the number of rows processed.
    """
    cols = list(df.columns)
    col_sql = ", ".join(f'"{c}"' for c in cols)
    conflict_sql = ", ".join(f'"{c}"' for c in conflict_cols)
 
    update_cols = [c for c in cols if c not in conflict_cols]
    if update_cols:
        update_sql = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
        on_conflict = f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
    else:
        on_conflict = f"ON CONFLICT ({conflict_sql}) DO NOTHING"
 
    sql = f'INSERT INTO "{table}" ({col_sql}) VALUES %s {on_conflict}'
 
    # Convert DataFrame rows to list of tuples; replace pd.NA / nan with None
    rows = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df.itertuples(index=False, name=None)
    ]
 
    execute_values(cur, sql, rows)
    return len(rows)


#----Sheet loaders-----------------------------------------------------------------------

def load_standard(sheet_name: str, date_col_raw: str = None) -> pd.DataFrame:
    """
    Loads a sheet where row 0 = headers, col 0 = date or key column.
    date_col_raw: the original header name for the date column (pre-clean).
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name, header=0)
    df.columns = [clean_col(c) for c in df.columns]

    #drop fully empty rows
    df.dropna(how="all", inplace=True)

    # Coerce date column
    date_col = clean_col(date_col_raw) if date_col_raw else df.columns[0]
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        df.dropna(subset=[date_col], inplace=True)
 
    # Replace 'n/a' strings with None
    df.replace("n/a", None, inplace=True)
    df.replace("N/A", None, inplace=True)
 
    return df


def load_job_site_ai() -> pd.DataFrame:
    """
    job_site_ai: col 0 is unnamed (date), row 0 has None in col 0.
    Rename col 0 → 'date'.
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="job_site_ai", header=0)
    df.columns = [clean_col(c) if str(c) != "None" else "date" for c in df.columns]
    # The first column ends up as 'none' after clean_col when header is None
    df.rename(columns={"none": "date"}, inplace=True)
    df.dropna(how="all", inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df.dropna(subset=["date"], inplace=True)
    # Strip trailing spaces from column names (Hybrid had a trailing space)
    df.columns = [c.strip() for c in df.columns]
    return df
 
 
def load_role_type_ai() -> pd.DataFrame:
    """
    role_type_ai: col 0 is unnamed (date), row 0 has None in col 0.
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="role_type_ai", header=0)
    cols = []
    for c in df.columns:
        cols.append("date" if str(c).strip() in ("None", "nan", "") else clean_col(c))
    df.columns = cols
    df.dropna(how="all", inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df.dropna(subset=["date"], inplace=True)
    return df


def load_company_jobs_ai() -> pd.DataFrame:
    """
    company_jobs_ai has TWO header rows:
      Row 0: Company names  (becomes column headers)
      Row 1: Industry names (extra metadata row — stored separately)
    We load both rows, melt into long format:
      date | company | industry | job_count
    """
    raw = pd.read_excel(EXCEL_PATH, sheet_name="company_jobs_ai", header=None)
 
    companies = list(raw.iloc[0])       # row 0: 'Company', Anthropic, Wells Fargo ...
    industries = list(raw.iloc[1])      # row 1: 'Industry', Research Services, ...
    data_rows = raw.iloc[2:].copy()     # row 2+: dates + counts
 
    # Build a mapping: company → industry (skip the label column at index 0)
    company_industry = {
        str(companies[i]).strip(): str(industries[i]).strip()
        for i in range(1, len(companies))
        if pd.notna(companies[i])
    }
 
    # Assign column names = companies (col 0 → 'date')
    data_rows.columns = ["date"] + [str(c).strip() for c in companies[1:]]
    data_rows["date"] = pd.to_datetime(data_rows["date"], errors="coerce").dt.date
    data_rows.dropna(subset=["date"], inplace=True)
 
    # Melt wide → long
    long = data_rows.melt(id_vars=["date"], var_name="company", value_name="job_count")
    long["industry"] = long["company"].map(company_industry)
    long["job_count"] = pd.to_numeric(long["job_count"], errors="coerce")
    long.dropna(subset=["job_count"], inplace=True)
    long["job_count"] = long["job_count"].astype(int)
 
    # Clean column names
    long.columns = [clean_col(c) for c in long.columns]
    return long[["date", "company", "industry", "job_count"]]


def load_state_employers_ai() -> pd.DataFrame:
    """
    state_employers_ai - long format: date | state | company | job_count
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="state_employers_ai", header=0)
    df.columns = [clean_col(c) for c in df.columns]
    df.dropna(how="all", inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df.dropna(subset=["date"], inplace=True)
    return df

def load_global_employers_ai() -> pd.DataFrame:
    """
    global_employers_ai - long format: date | country | company | job_count
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="global_employers_ai", header=0)
    df.columns = [clean_col(c) for c in df.columns]
    df.dropna(how="all", inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df.dropna(subset=["date"], inplace=True)
    return df
   
 
def main():
    print("=" * 60)
    print("  CAIO ETL → ai_job_market (localhost)")
    print("=" * 60)
 
    # ── Load all sheets ──
    print("\n[1/2] Loading Excel sheets ...")
 
    sheets = {
        "global_jobs_ai":     (load_standard("global_jobs_ai",     "Date"),    ["date"]),
        "job_site_ai":        (load_job_site_ai(),                              ["date"]),
        "global_employers_ai":(load_global_employers_ai(),                         ["date", "country", "company"]),
        "company_jobs_ai":    (load_company_jobs_ai(),                          ["date", "company"]),
        "industry_jobs_ai":   (load_standard("industry_jobs_ai",    "Date"),["date"]),
        "role_type_ai":       (load_role_type_ai(),                             ["date"]),
        "us_states_ai":       (load_standard("us_states_ai",        "Date"),    ["date"]),
        "state_employers_ai": (load_state_employers_ai(),                       ["date","state", "company"]),
    }
 
    for name, (df, _) in sheets.items():
        print(f"   ✓ {name:<25} {len(df):>5} rows  |  cols: {list(df.columns)[:4]} ...")
 
    # ── Connect & upsert ──
    print("\n[2/2] Connecting to PostgreSQL ...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        cur = conn.cursor()
        print(f"   ✓ Connected to '{DB_CONFIG['dbname']}' on {DB_CONFIG['host']}\n")
    except Exception as e:
        print(f"\n   ✗ Connection failed: {e}")
        print("     Check your .env credentials and that PostgreSQL is running.")
        return
 
    total_rows = 0
    errors = []
 
    for table_name, (df, conflict_cols) in sheets.items():
        try:
            count = upsert(cur, table_name, df, conflict_cols)
            conn.commit()
            total_rows += count
            print(f"   ✓ {table_name:<25} {count:>5} rows upserted")
        except Exception as e:
            conn.rollback()
            errors.append((table_name, str(e)))
            print(f"   ✗ {table_name:<25} FAILED → {e}")
 
    cur.close()
    conn.close()
 
    print(f"\n{'=' * 60}")
    print(f"  Done.  {total_rows} total rows upserted across {len(sheets)} tables.")
    if errors:
        print(f"\n  ⚠ {len(errors)} table(s) had errors:")
        for t, msg in errors:
            print(f"     • {t}: {msg}")
    print("=" * 60)
 
 
if __name__ == "__main__":
    main()
 
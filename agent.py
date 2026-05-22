"""
agent.py
--------
AI Job Market Analytics Agent.
Accepts a natural language question, generates SQL using Claude,
executes it against PostgreSQL, and returns a plain-English insight.

Usage:
    python agent.py
    (launches interactive CLI session)
"""

import os
import json
import anthropic
from dotenv import load_dotenv
from db import run_query, test_connection

load_dotenv()

# ── Load schema context (system prompt) ───────────────────────────────────────
SCHEMA_CONTEXT_PATH = "schema_context.md"

def load_schema_context() -> str:
    try:
        with open(SCHEMA_CONTEXT_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"schema_context.md not found. Make sure it is in the same "
            f"directory as agent.py."
        )

# ── Anthropic client ───────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

# ── Step 1: Generate SQL from natural language question ───────────────────────
def generate_sql(question: str, schema_context: str) -> tuple[str, str | None]:
    """
    Sends the user question to Claude with the schema context as system prompt.
    Asks Claude to return ONLY a JSON object with keys:
        - sql: the SELECT query to run
        - reasoning: brief explanation of the approach

    Returns:
        (sql_string, error)
    """
    prompt = f"""
The user wants to know: "{question}"

Your task:
1. Write a single, valid PostgreSQL SELECT query that answers this question.
2. Use only the tables and columns defined in your schema context.
3. Return ONLY a JSON object in this exact format with no other text:

{{
  "sql": "<your SELECT query here>",
  "reasoning": "<one sentence explaining your approach>"
}}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=schema_context,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude added them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        return parsed.get("sql", ""), None

    except json.JSONDecodeError as e:
        return "", f"Failed to parse SQL response as JSON: {e}\nRaw response: {raw}"
    except Exception as e:
        return "", f"Claude API error during SQL generation: {e}"


# ── Step 2: Generate insight narrative from query results ─────────────────────
def generate_insight(question: str, sql: str, rows: list[dict], schema_context: str) -> str:
    """
    Sends the query results back to Claude and asks for a plain-English insight.
    Output is formatted for PowerPoint bullets (2-3 sentences max).
    """
    # Limit rows sent to Claude to avoid token bloat — 50 rows is plenty
    sample = rows[:50]
    results_str = json.dumps(sample, indent=2, default=str)

    prompt = f"""
The user asked: "{question}"

You ran this SQL query:
{sql}

The query returned these results:
{results_str}

Your task:
Write a concise insight (2-3 sentences) suitable for a PowerPoint bullet point.
- Lead with the headline finding and the key number
- Include the week-over-week change if the data supports it
- Flag anything notably high, low, or unusual
- Be direct and specific — no filler phrases like "It is worth noting that..."
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=schema_context,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

    except Exception as e:
        return f"Claude API error during insight generation: {e}"


# ── Main agent function ────────────────────────────────────────────────────────
def ask(question: str, schema_context: str, verbose: bool = False) -> str:
    """
    Full agent pipeline:
        question → SQL generation → DB execution → insight narrative

    Args:
        question: natural language question about the AI job market
        schema_context: loaded schema_context.md content
        verbose: if True, prints the generated SQL and raw row count

    Returns:
        Plain-English insight string
    """
    # Step 1: Generate SQL
    sql, sql_error = generate_sql(question, schema_context)
    if sql_error:
        return f"⚠️ SQL generation failed:\n{sql_error}"

    if verbose:
        print(f"\n📋 Generated SQL:\n{sql}\n")

    # Step 2: Execute query
    rows, db_error = run_query(sql)
    if db_error:
        return f"⚠️ Query execution failed:\n{db_error}\n\nSQL attempted:\n{sql}"

    if not rows:
        return "⚠️ Query returned no results. The table may be empty or the date range returned nothing."

    if verbose:
        print(f"📊 Rows returned: {len(rows)}\n")

    # Step 3: Generate insight
    insight = generate_insight(question, sql, rows, schema_context)
    return insight


# ── Interactive CLI ────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  AI Job Market Analytics Agent")
    print("=" * 60)

    # Test DB connection first
    if not test_connection():
        print("Exiting — fix database connection before running the agent.")
        return

    # Load schema context
    try:
        schema_context = load_schema_context()
        print("✅ Schema context loaded.\n")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    print("Ask a question about the AI job market (or type 'quit' to exit).")
    print("Type 'verbose' to toggle SQL output on/off.\n")

    verbose = False

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("Goodbye.")
            break

        if user_input.lower() == "verbose":
            verbose = not verbose
            print(f"Verbose mode {'ON' if verbose else 'OFF'}.\n")
            continue

        print("\nAgent: Thinking...\n")
        insight = ask(user_input, schema_context, verbose=verbose)
        print(f"Agent: {insight}\n")
        print("-" * 60)


if __name__ == "__main__":
    main()
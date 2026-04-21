# Flask Expense Tracker (Idempotent POST)

Simple Flask + SQLite expense tracker with server-rendered forms (no JavaScript).

## Tech Stack

- Python 3.x
- Flask
- SQLite
- HTML + CSS (Jinja2 templates)

## Project Structure

- app.py
- schema.sql
- templates/index.html
- static/style.css
- requirements.txt

## Setup

1. Create and activate a Python virtual environment (recommended).
2. Install dependencies:

	```bash
	pip install -r requirements.txt
	```

3. Run the app:

	```bash
	python app.py
	```

4. Open http://127.0.0.1:5000

## API Behavior

### POST /expenses

- Accepts `X-Idempotency-Key` header.
- Also accepts `idempotency_key` form field for no-JS browser form submissions.
- If the idempotency key already exists:
  - API (JSON/Accept: application/json): returns `200 OK` with the existing record.
  - Browser form submit: does not create a duplicate row and redirects back to the list.
- If key is new: creates a row and returns `201 Created` (JSON) or redirects after POST.

### GET /expenses

- Supports filter query param: `category`
- Supports sort query param: `sort=date_desc` (default) or `sort=date_asc`
- Shows only filtered rows and computes `Total: ₹...` for visible rows only.

## Why Idempotency Here?

Expense submissions are sensitive to accidental retries (refresh, network retry, double-click). A unique idempotency key guarantees one logical create operation maps to one database row. Replays return the original record instead of inserting duplicates.

## Why SQLite?

SQLite is a good fit for a lightweight, single-service app:

- Zero external database setup
- Reliable ACID transactions
- Easy local development and testing
- Sufficient for small-to-medium, low-concurrency workloads

## Data Model

`expenses` table:

- `id` TEXT PRIMARY KEY (UUID)
- `amount` INTEGER (stored as cents/paisa to avoid floating-point errors)
- `category` TEXT
- `description` TEXT
- `date` DATE
- `created_at` TIMESTAMP
- `idempotency_key` TEXT UNIQUE
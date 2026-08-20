# Block Epi Info — Streamlit + AWS PostgreSQL

Python/Streamlit port of the original R Shiny "Block Epi Info" NTEP data-capture
app, backed by AWS PostgreSQL. See `/home/aswath/.claude/plans/humming-splashing-stearns.md`
for the full PRD (roles, data model, calculation logic, phased plan).

## 1. One-time setup

1. **Install dependencies** (Python >= 3.10 recommended):
   ```bash
   cd streamlit_app
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure secrets.** Copy the template and fill in your real AWS
   Postgres credentials and a master-admin bootstrap password:
   ```bash
   cp .streamlit/secrets_example.toml .streamlit/secrets.toml
   # edit .streamlit/secrets.toml with real values
   ```
   `.streamlit/secrets.toml` is gitignored — never commit it.

3. **Create the schema, seed locations, and bootstrap the master admin.**
   Run once:
   ```bash
   python scripts/init_db.py
   ```
   This creates `master_locations`, `users`, `entries` tables; seeds
   `master_locations` from `data/master_locations_seed.csv` (692 real
   Karnataka + Telangana blocks) if it's empty; and creates one master-admin
   account from the `[bootstrap]` values in secrets.toml if none exists yet.

4. **Run the app:**
   ```bash
   streamlit run app.py
   ```

5. Log in as the bootstrap master-admin account, go to **User Management**,
   and:
   - Change your own password (Edit a user → Reset password).
   - Bulk-upload state/district/block user credentials via CSV (template
     downloadable in that screen), or add individual accounts.

## 2. Deploying on Streamlit Community Cloud

1. Push this `streamlit_app/` folder to a GitHub repo (secrets.toml stays out
   via `.gitignore`).
2. Create the app on Streamlit Community Cloud pointing at `app.py`.
3. In the app's **Settings → Secrets** panel, paste the same key/value
   structure as `.streamlit/secrets_example.toml`, filled with your real
   AWS Postgres credentials — this is fed to the app as `st.secrets` exactly
   as a local `secrets.toml` would be.
4. Before first traffic, run `python scripts/init_db.py` once against the
   same database from your local machine (with your local `secrets.toml`
   pointed at the same AWS instance) to create the schema and bootstrap the
   master admin.

## 3. If new fields are added later

If `data/field_metadata.csv` changes (e.g. a new indicator column), run:
```bash
python scripts/migrate_db.py
```
This only adds missing columns to `entries` — never drops or renames
anything, never touches existing data.

## 4. Roles (see PRD for full detail)

- **Master Admin** — dashboard/export (unfiltered), Master Location List,
  Backend Data push (5 Nikshay/TBMB-sourced fields, single + bulk CSV), User
  Management. Does not edit the other 179 field-staff fields directly.
- **State user** — data entry for any block in their assigned state; sees a
  filtered dashboard + export only if `dashboard_access` is granted.
- **District user** — data entry for any block in their assigned district;
  same dashboard/export gating as state users, filtered to their district.
- **Block user** — data entry for exactly one fixed block; no dashboard.

State/district/block accounts are provisioned via the unified bulk-CSV
upload in User Management: `Username, Password, State, District, Block,
DashboardAccess` (leave District blank for state scope, leave Block blank
for district scope, fill all three for block scope).

## 5. Known UI/behavior notes vs. the R app

- Streamlit has no exact equivalent of shinydashboard's AdminLTE skin or its
  persistent multi-tab sidebar; `style/custom.css` approximates the same
  color language (header/sidebar/box/button colors, status labels). A
  side-by-side visual-parity pass against the running R app is recommended
  before rollout (see PRD Phase 6).
- Cross-section live recalculation (e.g. NAAT capacity, which depends on a
  field from a different section) updates on the next rerun/tab switch
  rather than instantaneously across simultaneously-mounted tabs, since
  Streamlit renders one section at a time. Values are always correct once
  saved; this only affects on-screen immediacy while both fields aren't
  visible together.
- Numeric fields support a true blank/empty state (`st.number_input(...,
  value=None)`), matching the R app's optional-numeric behavior; this
  requires Streamlit >= 1.23 (pinned >= 1.38 in requirements.txt).

# Pennywise

Pennywise is a student-focused personal finance application for recording income and spending, setting category budgets, tracking savings goals, and viewing a clear monthly financial overview. It is designed as a school qualification project with a practical Flask API, a responsive browser interface, and MongoDB Atlas persistence.

## Technology stack

- **Backend:** Python 3.11+, Flask 3, Werkzeug, Flask-CORS
- **Database:** MongoDB Atlas, PyMongo, MongoDB `Decimal128` for money
- **Frontend:** semantic HTML5, responsive CSS, and browser-native JavaScript
- **Authentication:** signed Flask session cookie and Werkzeug password hashing
- **Testing:** Python `unittest` integration tests against a configured test database

## Architecture

The Flask application serves both the JSON API and the static frontend from one origin. Routes are grouped into Flask blueprints. Authentication and authorization decorators resolve the signed-in user from the server-managed session. All user-owned database queries add the authenticated `user_id`; IDs sent by the browser never determine ownership.

Financial calculations are centralized in `Backend/utils/finance.py`. Money enters the system through strict decimal validation, is stored as `Decimal128`, is calculated with Python `Decimal`, and is returned as two-decimal strings. Budget warnings are calculated dynamically from transactions and budget limits rather than stored as notification records.

## Folder structure

```text
Pennywise/
├── .env.example
├── .gitignore
├── README.md
├── Backend/
│   ├── app.py
│   ├── config.py
│   ├── database.py
│   ├── requirements.txt
│   ├── routes/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── categories.py
│   │   ├── expenses.py
│   │   ├── income.py
│   │   ├── overview.py
│   │   ├── savings_goals.py
│   │   ├── transactions.py
│   │   └── users.py
│   ├── tests/
│   │   ├── test_phase2.py
│   │   ├── test_phase3.py
│   │   ├── test_phase4.py
│   │   └── test_phase5.py
│   └── utils/
│       ├── auth.py
│       ├── finance.py
│       ├── users.py
│       └── validators.py
└── Frontend/
    ├── index.html
    ├── login.html
    ├── register.html
    ├── overview.html
    ├── transactions.html
    ├── budgets.html
    ├── goals.html
    ├── profile.html
    ├── admin.html
    ├── css/style.css
    └── js/
```

## MongoDB Atlas setup

1. Create a free MongoDB Atlas project and cluster.
2. In **Database Access**, create a database user. This database username and password are separate from the Atlas website login.
3. Grant the database user read/write access to the Pennywise database.
4. In **Network Access**, allow the IP address of the computer running Pennywise.
5. Open **Connect → Drivers**, choose Python, and copy the `mongodb+srv://...` connection string.
6. Replace the username, password, and cluster placeholders. Percent-encode special characters in credentials.
7. Put the finished URI only in the local `.env` file. Never paste it into source files or commit it.

Pennywise creates the required collections, indexes, and default categories at startup when Atlas is reachable.

## Environment variables

Copy `.env.example` to `.env` and provide these values:

```dotenv
MONGO_URI=mongodb+srv://DATABASE_USER:DATABASE_PASSWORD@YOUR_CLUSTER.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=pennyswise
SECRET_KEY=replace-with-a-long-random-secret
```

Required variables:

- `MONGO_URI`: MongoDB connection string. It must remain private.
- `DATABASE_NAME`: database name; the project default is `pennyswise`.
- `SECRET_KEY`: long random value used to sign session cookies. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.

Optional deployment variables are `SESSION_COOKIE_SECURE=true`, `CORS_ORIGINS=https://your-frontend.example`, and `MONGO_TIMEOUT_MS=5000`. Keep `CORS_ORIGINS` empty for normal same-origin local use.

## Installation and local run

From the `Pennywise` folder in Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Backend\requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, then start the application without changing PowerShell's script policy:

```powershell
.\.venv\Scripts\python.exe Backend\app.py
```

Open `http://127.0.0.1:5000`. The built-in Flask server is for local development and demonstrations, not public production hosting.

To promote an existing account to the initial administrator, run from the `Backend` folder while the same environment variables are configured:

```powershell
..\.venv\Scripts\python.exe -m flask --app app promote-admin user@example.com
```

## API overview

All normal application responses are JSON with a `success` Boolean. Failed API requests also contain a safe `message`; validation responses can include an `errors` object.

| Area | Method and path | Purpose |
|---|---|---|
| Health | `GET /api/health` | Application health |
| Health | `GET /api/health/database` | Safe MongoDB connection status |
| Authentication | `POST /api/auth/register` | Register and start a session |
| Authentication | `POST /api/auth/login` | Log in |
| Authentication | `POST /api/auth/logout` | Log out |
| Authentication | `GET /api/auth/me` | Current session user |
| Profile | `GET, PUT, DELETE /api/users/me` | View, edit, or delete own account |
| Categories | `GET /api/categories` | List shared categories |
| Categories | `POST /api/categories` | Create category (admin) |
| Categories | `PUT, DELETE /api/categories/<id>` | Edit/delete category (admin) |
| Income | `GET, POST /api/income` | List or create own income records |
| Income | `PUT, DELETE /api/income/<id>` | Edit/delete own income record |
| Budgets | `GET, POST /api/expenses` | Monthly progress or create own category budget |
| Budgets | `PUT, DELETE /api/expenses/<id>` | Edit/delete own budget |
| Transactions | `GET, POST /api/transactions` | Search/filter or create own transactions |
| Transactions | `GET, PUT, DELETE /api/transactions/<id>` | View/edit/delete own transaction |
| Goals | `GET, POST /api/savings-goals` | List/create own savings goals |
| Goals | `GET, PUT, DELETE /api/savings-goals/<id>` | View/edit/delete own goal |
| Overview | `GET /api/overview` | Monthly totals, trend, budgets, and recent activity |
| Admin | `GET /api/admin/users` | List users (admin) |
| Admin | `GET, PUT, DELETE /api/admin/users/<id>` | View/edit/delete user (admin) |
| Admin | `GET /api/admin/statistics` | System counts (admin) |

Transaction list parameters include `search`, `type`, `category_id`, `from`, and `to`. Category lists can be restricted with `type=income` or `type=expense`. Budget and overview requests accept `month=YYYY-MM`.

## Database collections and relationships

- `users`: account, hashed password, profile settings, currency, and `role`. `user_id`, username, and email are unique.
- `income`: simple income records owned by `user_id`; each amount keeps its original currency.
- `expenses`: one monthly category budget per user/category pair. Each amount keeps its original currency, and each record references an expense category.
- `transactions`: income or expense activity owned by a user. Each record keeps its original decimal amount and currency, and references a category with the same type.
- `categories`: shared labels with an explicit `income` or `expense` type, identified by `category_id`. Only administrators can change them.
- `savings_goals`: user-owned targets with target amount, current amount, currency, and deadline.

`users.user_id` is the ownership key for income, expenses, transactions, and savings goals. Category references connect transactions and budgets to the shared category list. User deletion removes all records owned by that user. Category deletion is rejected while a transaction or budget references it.

Indexes cover unique business IDs, unique usernames/emails, user ownership fields, transaction dates/categories, expense categories, and the unique user/category budget relationship.

Displayed amounts and totals are converted to the user's preferred currency with Frankfurter reference rates. Rates are cached in memory for six hours by default; a cached stale rate is used during a temporary provider outage, while requests fail clearly if no trustworthy rate is available. Configure this with `EXCHANGE_RATE_API_URL`, `EXCHANGE_RATE_CACHE_SECONDS`, and `EXCHANGE_RATE_TIMEOUT_SECONDS`.

## Authentication and security

- Passwords are hashed by Werkzeug and are never returned by serializers or administrator endpoints.
- Authentication uses a signed, `HttpOnly`, `SameSite=Lax` session cookie. Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS.
- Login and registration clear older session data before establishing the new identity.
- Protected routes load the current database user on every request; administrator routes also require `role = "admin"`.
- User-owned queries always combine the resource ID with the authenticated session's `user_id`, preventing IDOR access.
- JSON validation rejects invalid dates, categories, negative/zero money where not allowed, excessive amounts, invalid roles, and past goal deadlines.
- Unsafe API methods reject untrusted cross-site origins. Optional CORS access is explicit and credential-aware.
- Security headers restrict framing, scripts, object content, referrers, and unnecessary browser capabilities.
- API responses are not cached and error handlers return safe JSON without stack traces or connection credentials.
- Request bodies are limited to 64 KiB. Debug mode is disabled.
- Frontend content originating from users is rendered through `textContent`, not HTML injection.
- `.env`, keys, certificates, logs, virtual environments, and coverage output are ignored by Git.

For an internet-facing deployment, add infrastructure-level HTTPS, persistent rate limiting, monitoring, backups, and a production WSGI server.

## Administrator functionality

Administrators can view users, change user roles and profile fields through the API, delete users with their related data, manage the shared category list, and view system-wide record counts. A normal user receives HTTP 403 for administrator endpoints and category mutations. The API prevents an administrator from removing their own admin role or deleting their own account from the administrator page.

## Testing

The integration tests use the database configured in `.env`; they create uniquely prefixed temporary data and remove it afterward. Do not point tests at a database where similarly prefixed test data must be preserved.

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s Backend\tests -v
```

The suite verifies registration, login/logout, profiles, administrator authorization, categories, income, transactions, budgets, goals, overview calculations, Decimal128 storage, search and filters, cross-user isolation, notifications, indexes, safe errors, and validation edge cases. Tests skip cleanly when MongoDB Atlas is unavailable.

## GitHub usage

Before committing, run `git status` and confirm that `.env`, certificate/key files, logs, and virtual environments are absent. Commit `.env.example` only with blank values. A typical workflow is:

```powershell
git init
git add .
git status
git commit -m "Complete Pennywise qualification project"
```

Push to a private or public GitHub repository only after inspecting the staged changes for secrets. If a database URI or secret was ever committed, rotate it in Atlas or the deployment environment and remove it from Git history; merely deleting the current file is insufficient.

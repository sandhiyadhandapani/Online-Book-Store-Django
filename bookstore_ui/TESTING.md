# BookStore QA & Testing Documentation (Team 4: AI Integration & Testing)

This document outlines the testing strategy, test execution instructions, test coverage areas, manual QA verification checklist, and deployment readiness findings for the BookStore Django application.

---

## 1. How to Run the Automated Test Suite

Ensure the virtual environment is activated and you are in the `bookstore_ui` directory.

### Run All Tests
```bash
python manage.py test
```

### Run Specific Test Suites
- **AI Summary & Gemini Integration Tests:**
  ```bash
  python manage.py test store.tests.AISummaryTests
  ```
- **Smoke Tests (Public URLs, Auth & Protected Redirects):**
  ```bash
  python manage.py test store.tests.SmokeTests
  ```
- **Catalog, Search, Filter & Role Tests:**
  ```bash
  python manage.py test store.tests.StoreTests
  ```
- **Cart & Pricing Tests:**
  ```bash
  python manage.py test store.tests.CartTests
  ```
- **Orders, Checkout & Wishlist Tests:**
  ```bash
  python manage.py test store.tests.Team3Tests
  ```

### Run with Detailed Verbosity
```bash
python manage.py test -v 2
```

---

## 2. Test Areas Covered

### A. AI Integration & Gemini Service (`store.ai`)
- **Success & Caching:** Summaries generated via Gemini API are parsed, cleaned of markdown, clamped to 700 chars, and stored in the database (`ai_summary` and `ai_summary_updated`). Subsequent requests serve from the database without invoking the external API.
- **Staff-Only Refresh:** Staff users can force regeneration with `refresh=1`; non-staff requests with `refresh=1` are safely ignored and serve cached content.
- **Strict Prompt Sandboxing:** The AI prompt is built solely from sanitized database attributes (`title`, `author`, `category`) to eliminate prompt injection risks.
- **Resilience & Fault Tolerance:**
  - Missing or empty API key returns clean user-safe error without crashing or writing junk to the database.
  - Timeouts and connection failures return friendly messages without exposing system internals.
  - HTTP 403 / 400 (invalid API credentials) return authentication failure status without logging credentials.
  - HTTP 429 (rate limiting) triggers an automatic single retry after a 2-second sleep, recovering gracefully when possible.
  - Blocked safety responses, empty candidate lists, and malformed JSON payloads are handled safely.
- **Client Rate Limiting:** Django cache sliding-window rate limit enforces a maximum of 5 generation requests per minute per client (by session key or IP address), returning HTTP 429 when exceeded. Reading cached summaries does not consume the rate limit quota.
- **Credential Security:** Gemini API keys are never rendered in templates, JavaScript variables, or JSON responses.

### B. Admin AI Controls
- `BookAdmin` provides `ai_summary` and `ai_summary_updated` in a dedicated **AI Summary** fieldset.
- Admin action **"Clear AI summary"** bulk-resets summaries for selected books.
- Admin action **"Generate AI summary"** batches generation for up to 10 books at once, guarding against bulk API overconsumption.

### C. Store Smoke & Regression Coverage
- Full status verification across public guest endpoints (`/`, `/books/`, `/books/<id>/`, `/cart/`, `/login/`, `/register/`, `/newsletter/`, and 404).
- Verification that authenticated users accessing `/login/` or `/register/` are redirected to `/`.
- Verification that unauthorized guests accessing `/dashboard/` or `/dashboard/books/` are redirected to `/admin/login/`.

---

## 3. Manual QA Checklist Table

| Page | Action | Expected Result | Status |
| :--- | :--- | :--- | :--- |
| **Home** (`/`) | Load page | Navbar, Best Sellers, New Arrivals, and Categories render cleanly; cart and wishlist badges display correct totals. | Pass |
| **Listing** (`/books/`) | Search by query keyword `Atomic` | Filters books to matching title/author/category. | Pass |
| **Listing** (`/books/`) | Apply Category filter (e.g. Fiction) | Only books belonging to Fiction are listed. | Pass |
| **Listing** (`/books/`) | Filter by price range (e.g. `250-500`) | Books within ₹250 to ₹500 are displayed. | Pass |
| **Listing** (`/books/`) | Sort by "Price: High to Low" | Listing orders from highest price to lowest. | Pass |
| **Detail** (`/books/<id>/`) | Open book with no AI summary | Displays "AI Book Summary" box with `#aiBtn` labeled "Generate Summary" and disclaimer label. | Pass |
| **Detail** (`/books/<id>/`) | Click "Generate Summary" with valid key | Button enters loading state ("Generating..."), summary appears in `#aiOut` via textContent, button updates or hides. | Pass |
| **Detail** (`/books/<id>/`) | Refresh page after summary generated | Cached summary renders instantly on page load without calling external API. Non-staff does not see "Regenerate summary". | Pass |
| **Detail** (`/books/<id>/`) | Click "Regenerate summary" as staff | Summary is refreshed from Gemini API and updated in the database. | Pass |
| **Detail** (`/books/<id>/`) | Click "Generate Summary" with invalid key | Button returns to retryable state, friendly error message shown in `#aiOut` in red text; no crashes or junk saved. | Pass |
| **Detail** (`/books/<id>/`) | Check Page Source / Network Tab | `GEMINI_API_KEY` is not present anywhere in HTML source, JavaScript, or response headers/bodies. | Pass |
| **Cart** (`/cart/`) | Add book to cart from detail page | Navbar badge increments; cart table displays title, quantity controls, price, discount savings, and total. | Pass |
| **Cart** (`/cart/`) | Adjust quantity / remove item | Totals update dynamically; stock constraints are respected. | Pass |
| **Checkout** (`/checkout/`) | Access checkout as guest | Redirects to `/login/?next=/checkout/`. | Pass |
| **Checkout** (`/checkout/`) | Submit valid order as logged-in user | Order is created with unique order number (`BS-YYYYMMDD-XXXX`), stock is deducted, cart is cleared, confirmation email sent to console. | Pass |
| **Orders** (`/orders/`) | View order list & detail | User sees their placed orders; cannot access orders placed by other users (returns 404). | Pass |
| **Wishlist** (`/wishlist/`) | Toggle heart button on book card/detail | Adds/removes book from wishlist via AJAX; header badge updates; persists to user account. | Pass |
| **Admin** (`/admin/store/book/`) | Edit book in Admin | Dedicated "AI Summary" fieldset displays `ai_summary` (editable) and `ai_summary_updated` (readonly). | Pass |
| **Admin** (`/admin/store/book/`) | Select books & run "Generate AI summary" | Generates summaries for up to 10 selected books; warns if more than 10 are selected. | Pass |
| **Admin** (`/admin/store/book/`) | Select books & run "Clear AI summary" | Clears summaries and timestamps for selected books. | Pass |
| **Dashboard** (`/dashboard/`) | Access as guest or regular user | Redirects to `/admin/login/`. Staff member sees operational statistics and inventory tables. | Pass |

---

## 4. Production Deployment Checklist (`python manage.py check --deploy`)

Running `python manage.py check --deploy` reports the following findings:

### Error (1)
- **`mail.E001` (Development Email Backend):**
  - *Finding:* `MAILERS` setting uses `django.core.mail.backends.console.EmailBackend`.
  - *Recommendation:* Configure production SMTP credentials (e.g. Amazon SES, SendGrid, or corporate SMTP) in `.env` before production deployment.

### Warnings (6)
- **`security.W004` (`SECURE_HSTS_SECONDS`):**
  - *Finding:* HTTP Strict Transport Security (HSTS) is not enabled.
  - *Recommendation:* Enable `SECURE_HSTS_SECONDS = 31536000` (along with `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD`) once the site is served exclusively over HTTPS.
- **`security.W008` (`SECURE_SSL_REDIRECT`):**
  - *Finding:* Automatic HTTP to HTTPS redirection is disabled (`False`).
  - *Recommendation:* Set `SECURE_SSL_REDIRECT = True` or handle HTTP-to-HTTPS redirect at the reverse-proxy (Nginx/Cloudflare) layer.
- **`security.W009` (`SECRET_KEY` Insecure Fallback):**
  - *Finding:* Fallback secret key prefixed with `'django-insecure-'` is detected if no environment variable is present.
  - *Recommendation:* Ensure a strong, randomly generated 50+ character secret key is defined in production `.env`.
- **`security.W012` (`SESSION_COOKIE_SECURE`):**
  - *Finding:* Session cookie is not restricted to HTTPS connections.
  - *Recommendation:* Set `SESSION_COOKIE_SECURE = True` in production settings to prevent cookie transmission over plaintext HTTP.
- **`security.W016` (`CSRF_COOKIE_SECURE`):**
  - *Finding:* CSRF cookie is not restricted to HTTPS connections.
  - *Recommendation:* Set `CSRF_COOKIE_SECURE = True` in production settings to guard against CSRF token interception over plaintext connections.
- **`security.W018` (`DEBUG = True`):**
  - *Finding:* `DEBUG` evaluates to `True` when `DEBUG` environment variable is omitted.
  - *Recommendation:* Ensure `DEBUG=False` is set in production environment variables to avoid exposing sensitive debug tracebacks to end users.

# BookStore - Backend Documentation

This document describes backend management commands, data seeding, models, and third-party integrations.

## Google Books API Importer

The `import_books` command populates the database with real books across 6 categories using the Google Books API:
- **Fiction** (`bi-book`)
- **Non-Fiction** (`bi-journal-text`)
- **Education** (`bi-mortarboard`)
- **Technology** (`bi-cpu`)
- **Business** (`bi-briefcase`)
- **Health & Fitness** (`bi-heart-pulse`)

### Command Usage

```bash
# Curated import of 20+ books with verified covers
python manage.py import_books --curated

# Standard import (12 books per category)
python manage.py import_books

# Import real books and clear old dummy seed books
python manage.py import_books --per-category 12 --clear-dummy

# Dry-run mode: preview import without writing to database
python manage.py import_books --dry-run

# Clean missing or placeholder covers
python manage.py clean_covers [--dry-run]
```

### Setting Google Books API Key

An API key is optional because the command works unauthenticated and includes fallback handling for rate-limited requests. However, providing a key provides higher rate limits.

1. Generate a free API key from the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) with the Books API enabled.
2. Create or open the `.env` file in the project root:
   ```env
   GOOGLE_BOOKS_API_KEY=AIzaSyYourGoogleBooksApiKeyHere
   ```
3. Run the import command:
   ```bash
   python manage.py import_books --curated
   ```

### Features & Safety Controls

- **Order Protection**: `--clear-dummy` and `clean_covers` delete dummy or invalid-cover books that have no orders. If a book is referenced in an `OrderItem`, the command keeps the book, sets `is_active=False`, and prints a warning.
- **Idempotency**: Running the command multiple times will not duplicate books (checked by case-insensitive title + author pair and unique slug).
- **Atomic Transactions**: Book creation is wrapped in `transaction.atomic`.
- **Cover Image Validation & Fallback**: Validates image content type, byte size (4 KB to 2 MB), dimensions (>= 150x200), and rejects Google placeholder hash. Automatically falls back to Open Library via ISBN-13/ISBN-10.
- **Badges**: Automatically marks the 4 highest-rated active books with valid covers as `is_best_seller=True` and the 4 most recently published as `is_new_arrival=True`.

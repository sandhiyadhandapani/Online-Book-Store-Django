# BookStore - Team 1 (Frontend & UI)

Run:
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py setup_roles
    python manage.py import_books --curated
    python manage.py createsuperuser
    python manage.py runserver

Pages: /  /books/  /books/1/  /cart/  /checkout/  /newsletter/  /dashboard/  /dashboard/books/

## Google Books Import Command

Real books from the Google Books API can be imported with covers, descriptions, and categories:

```bash
# Basic usage (defaults to 12 books per category)
python manage.py import_books

# Clear old dummy seed books and import 12 real books per category
python manage.py import_books --per-category 12 --clear-dummy

# Test run without saving changes to the database
python manage.py import_books --dry-run
```

### Google Books API Key (Optional)
The importer works without an API key. To increase API quota and avoid unauthenticated rate limits, obtain an API key from Google Cloud Console and set it in `.env`:

```env
GOOGLE_BOOKS_API_KEY=your_api_key_here
```

Files owned by Team 1: templates/ and static/ (css, js).
Template variable names:
  book/b: id, title, author, price, old_price, rating, pct, reviews, cover_image
  cats: (name, icon, count)   cart_count   items/subtotal/discount/shipping/total (checkout)
Hooks for other teams:
  Team 2 - filter form in books.html (GET: cat, price, rating, q, sort), pager links
  Team 3 - Add to Cart form in book_detail.html, checkout form, newsletter form (POST email)
  Team 4 - #aiBtn in book_detail.html (data-url) + static/js/main.js demo block

import hashlib
import io
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from PIL import Image
from store.models import Category, Book, Subscriber, Order, OrderItem


def make_valid_test_jpeg(width=300, height=400):
    img = Image.new("RGB", (width, height))
    pixels = [(x % 256, y % 256, (x * y) % 256) for y in range(height) for x in range(width)]
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

User = get_user_model()


class StoreTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create categories
        self.cat_fiction = Category.objects.create(name="Fiction", icon="bi-book")
        self.cat_tech = Category.objects.create(name="Technology", icon="bi-cpu")
        self.cat_nonfiction = Category.objects.create(name="Non-Fiction", icon="bi-journal-text")
        self.cat_business = Category.objects.create(name="Business", icon="bi-briefcase")

        # Create 14 active books to test pagination (12 on page 1, 2 on page 2)
        # Varying prices and ratings to test filters and sorting
        books_setup = [
            ("Atomic Habits", "James Clear", self.cat_nonfiction, Decimal("499.00"), Decimal("799.00"), 4.8, 2400, True, False),
            ("The Psychology of Money", "Morgan Housel", self.cat_business, Decimal("399.00"), Decimal("599.00"), 4.7, 1900, True, False),
            ("Clean Code", "Robert C. Martin", self.cat_tech, Decimal("599.00"), Decimal("899.00"), 4.6, 1200, True, False),
            ("Dune", "Frank Herbert", self.cat_fiction, Decimal("449.00"), Decimal("699.00"), 4.8, 3100, True, False),
            ("It Ends With Us", "Colleen Hoover", self.cat_fiction, Decimal("349.00"), Decimal("499.00"), 4.5, 2700, False, True),
            ("Fourth Wing", "Rebecca Yarros", self.cat_fiction, Decimal("429.00"), Decimal("649.00"), 4.6, 1500, False, True),
            ("Think Like a Monk", "Jay Shetty", self.cat_nonfiction, Decimal("379.00"), Decimal("549.00"), 4.4, 980, False, True),
            ("The Midnight Library", "Matt Haig", self.cat_fiction, Decimal("359.00"), Decimal("499.00"), 4.5, 1600, False, True),
            ("Cheap Notes", "Author A", self.cat_fiction, Decimal("150.00"), None, 3.5, 50, False, False),
            ("Budget Primer", "Author B", self.cat_business, Decimal("220.00"), None, 2.5, 30, False, False),
            ("Mid Tech Guide", "Author C", self.cat_tech, Decimal("750.00"), None, 4.2, 400, False, False),
            ("Mid Story", "Author D", self.cat_fiction, Decimal("850.00"), None, 3.8, 300, False, False),
            ("Enterprise Architecture", "Author E", self.cat_tech, Decimal("1250.00"), None, 4.9, 500, False, False),
            ("Luxury Art Volume", "Author F", self.cat_nonfiction, Decimal("1800.00"), None, 4.1, 150, False, False),
        ]

        self.books = []
        for title, author, cat, price, old_price, rating, rev_count, best, new in books_setup:
            b = Book.objects.create(
                title=title,
                author=author,
                category=cat,
                price=price,
                old_price=old_price,
                rating=rating,
                reviews_count=rev_count,
                stock=20,
                is_best_seller=best,
                is_new_arrival=new,
                is_active=True
            )
            self.books.append(b)

        # Inactive book
        self.inactive_book = Book.objects.create(
            title="Hidden Inactive Book",
            author="Ghost Writer",
            category=self.cat_fiction,
            price=Decimal("100.00"),
            rating=1.0,
            reviews_count=0,
            stock=0,
            is_active=False
        )

        # Non-staff and staff users
        self.regular_user = User.objects.create_user(username="regular", password="password123")
        self.staff_user = User.objects.create_user(username="staff", password="password123", is_staff=True)

    def test_search(self):
        # 1. Search by title
        response = self.client.get(reverse("books"), {"q": "Clean Code"})
        self.assertEqual(response.status_code, 200)
        book_titles = [b.title for b in response.context["books"]]
        self.assertIn("Clean Code", book_titles)
        self.assertEqual(len(book_titles), 1)

        # 2. Search by author
        response = self.client.get(reverse("books"), {"q": "James Clear"})
        self.assertEqual(response.status_code, 200)
        book_titles = [b.title for b in response.context["books"]]
        self.assertIn("Atomic Habits", book_titles)

        # 3. Search by category name
        response = self.client.get(reverse("books"), {"q": "Technology"})
        self.assertEqual(response.status_code, 200)
        for b in response.context["books"]:
            self.assertEqual(b.category.name, "Technology")

    def test_category_filter(self):
        # Single category filter
        response = self.client.get(reverse("books"), {"cat": "Fiction"})
        self.assertEqual(response.status_code, 200)
        for b in response.context["books"]:
            self.assertEqual(b.category.name, "Fiction")

        # Multiple categories filter
        response = self.client.get(reverse("books"), {"cat": ["Fiction", "Technology"]})
        self.assertEqual(response.status_code, 200)
        for b in response.context["books"]:
            self.assertIn(b.category.name, ["Fiction", "Technology"])

    def test_price_filter(self):
        # 0-250
        res1 = self.client.get(reverse("books"), {"price": "0-250"})
        self.assertEqual(res1.status_code, 200)
        for b in res1.context["books"]:
            self.assertLessEqual(b.price, Decimal("250"))

        # 250-500
        res2 = self.client.get(reverse("books"), {"price": "250-500"})
        self.assertEqual(res2.status_code, 200)
        for b in res2.context["books"]:
            self.assertTrue(Decimal("250") <= b.price <= Decimal("500"))

        # 500-1000
        res3 = self.client.get(reverse("books"), {"price": "500-1000"})
        self.assertEqual(res3.status_code, 200)
        for b in res3.context["books"]:
            self.assertTrue(Decimal("500") <= b.price <= Decimal("1000"))

        # 1000-
        res4 = self.client.get(reverse("books"), {"price": "1000-"})
        self.assertEqual(res4.status_code, 200)
        for b in res4.context["books"]:
            self.assertGreaterEqual(b.price, Decimal("1000"))

    def test_sort(self):
        # Price: Low to High
        res_asc = self.client.get(reverse("books"), {"sort": "Price: Low to High"})
        self.assertEqual(res_asc.status_code, 200)
        prices = [b.price for b in res_asc.context["books"]]
        self.assertEqual(prices, sorted(prices))

        # Price: High to Low
        res_desc = self.client.get(reverse("books"), {"sort": "Price: High to Low"})
        self.assertEqual(res_desc.status_code, 200)
        prices = [b.price for b in res_desc.context["books"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

        # Top Rated
        res_rating = self.client.get(reverse("books"), {"sort": "Top Rated"})
        self.assertEqual(res_rating.status_code, 200)
        ratings = [b.rating for b in res_rating.context["books"]]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

    def test_pagination_page_2(self):
        # Total active books = 14, page size = 12
        response = self.client.get(reverse("books"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertEqual(len(response.context["books"]), 2)

    def test_inactive_book_returns_404(self):
        # Inactive book must return 404
        response = self.client.get(reverse("book_detail", args=[self.inactive_book.pk]))
        self.assertEqual(response.status_code, 404)

        # Inactive book must not appear in book list
        list_response = self.client.get(reverse("books"))
        all_listed_ids = [b.id for b in list_response.context["books"]]
        self.assertNotIn(self.inactive_book.pk, all_listed_ids)

    def test_duplicate_newsletter_email(self):
        email = "reader@example.com"

        # 1. First subscription
        res1 = self.client.post(reverse("newsletter"), {"email": email}, follow=True)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(Subscriber.objects.filter(email=email).count(), 1)
        msgs1 = [m.message for m in get_messages(res1.wsgi_request)]
        self.assertIn("Thanks for subscribing!", msgs1)

        # 2. Duplicate subscription with whitespace and uppercase
        res2 = self.client.post(reverse("newsletter"), {"email": f"  {email.upper()}  "}, follow=True)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(Subscriber.objects.filter(email=email).count(), 1)
        msgs2 = [m.message for m in get_messages(res2.wsgi_request)]
        self.assertIn("You are already subscribed.", msgs2)

        # 3. Invalid email
        res3 = self.client.post(reverse("newsletter"), {"email": "invalid-email-address"}, follow=True)
        self.assertEqual(res3.status_code, 200)
        msgs3 = [m.message for m in get_messages(res3.wsgi_request)]
        self.assertIn("Enter a valid email address.", msgs3)

    def test_dashboard_redirects_non_staff(self):
        # 1. Anonymous user redirected to admin login
        res_anon = self.client.get(reverse("dashboard"))
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn("/admin/login/", res_anon.url)

        # 2. Non-staff authenticated user redirected to admin login
        self.client.login(username="regular", password="password123")
        res_user = self.client.get(reverse("dashboard"))
        self.assertEqual(res_user.status_code, 302)
        self.assertIn("/admin/login/", res_user.url)
        self.client.logout()

        # 3. Staff user can access dashboard
        self.client.login(username="staff", password="password123")
        res_staff = self.client.get(reverse("dashboard"))
        self.assertEqual(res_staff.status_code, 200)
        self.assertIn("total_books", res_staff.context)
        self.assertIn("total_orders", res_staff.context)
        self.assertIn("total_subscribers", res_staff.context)
        self.assertIn("total_users", res_staff.context)

    def test_model_properties_and_slugs(self):
        book = self.books[0]  # Atomic Habits (rating 4.8, price 499, old_price 799, reviews 2400)
        self.assertEqual(book.pct, 96.0)
        self.assertEqual(book.reviews, 2400)
        self.assertEqual(book.discount_percent, 38)
        self.assertTrue(book.c1.startswith("#"))
        self.assertTrue(book.c2.startswith("#"))

        # Duplicate slug handling
        duplicate_book = Book.objects.create(
            title="Atomic Habits",
            author="Another Author",
            category=self.cat_nonfiction,
            price=Decimal("299.00")
        )
        self.assertNotEqual(duplicate_book.slug, book.slug)
        self.assertTrue(duplicate_book.slug.startswith("atomic-habits"))

    def test_setup_roles_command(self):
        call_command("setup_roles")
        from django.contrib.auth.models import Group
        cat_group = Group.objects.get(name="Catalog Manager")
        support_group = Group.objects.get(name="Support Staff")
        cat_perms = set(cat_group.permissions.values_list("codename", flat=True))
        support_perms = set(support_group.permissions.values_list("codename", flat=True))

        self.assertIn("add_book", cat_perms)
        self.assertIn("change_book", cat_perms)
        self.assertIn("delete_book", cat_perms)
        self.assertIn("view_book", cat_perms)
        self.assertIn("add_category", cat_perms)
        self.assertIn("view_order", cat_perms)

        self.assertIn("view_order", support_perms)
        self.assertIn("change_order", support_perms)
        self.assertIn("view_subscriber", support_perms)
        self.assertIn("view_book", support_perms)

        # Verify permissions on a user assigned to Catalog Manager
        user_cm = User.objects.create_user(username="cm_tester", password="password123")
        user_cm.groups.add(cat_group)
        user_cm = User.objects.get(pk=user_cm.pk)
        self.assertTrue(user_cm.has_perm("store.add_book"))
        self.assertTrue(user_cm.has_perm("store.change_book"))
        self.assertTrue(user_cm.has_perm("store.delete_book"))
        self.assertTrue(user_cm.has_perm("store.view_order"))
        self.assertFalse(user_cm.has_perm("store.change_order"))

        # Verify permissions on a user assigned to Support Staff
        user_ss = User.objects.create_user(username="ss_tester", password="password123")
        user_ss.groups.add(support_group)
        user_ss = User.objects.get(pk=user_ss.pk)
        self.assertTrue(user_ss.has_perm("store.view_order"))
        self.assertTrue(user_ss.has_perm("store.change_order"))
        self.assertTrue(user_ss.has_perm("store.view_subscriber"))
        self.assertFalse(user_ss.has_perm("store.delete_book"))

    def test_book_delete_and_permissions(self):
        book = self.books[8]
        delete_url = reverse("book_delete", kwargs={"pk": book.pk})

        # 1. Anonymous user redirected to login
        res_anon = self.client.post(delete_url)
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn("/admin/login/", res_anon.url)

        # 2. GET request not allowed (405)
        self.client.login(username="staff", password="password123")
        res_get = self.client.get(delete_url)
        self.assertEqual(res_get.status_code, 405)

        # 3. Staff without delete_book permission forbidden (403)
        res_no_perm = self.client.post(delete_url)
        self.assertEqual(res_no_perm.status_code, 403)
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())

        # 4. Staff with delete_book permission succeeds
        del_perm = Permission.objects.get(codename="delete_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(del_perm)
        self.staff_user = User.objects.get(pk=self.staff_user.pk)

        res_del = self.client.post(delete_url, follow=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())
        messages = [m.message for m in get_messages(res_del.wsgi_request)]
        self.assertIn("Book deleted", messages)

    def test_book_delete_protected_by_order(self):
        book = self.books[0]
        order = Order.objects.create(
            name="Alice",
            email="alice@example.com",
            phone="1234567890",
            address_line1="123 Main St",
            city="City",
            state="State",
            pin="123456",
            total_amount=Decimal("499.00")
        )
        OrderItem.objects.create(
            order=order,
            book=book,
            quantity=1,
            price=book.price
        )

        del_perm = Permission.objects.get(codename="delete_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(del_perm)
        self.client.login(username="staff", password="password123")

        delete_url = reverse("book_delete", kwargs={"pk": book.pk})
        res = self.client.post(delete_url, follow=True)
        self.assertEqual(res.status_code, 200)

        # Book is NOT deleted
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())
        messages = [m.message for m in get_messages(res.wsgi_request)]
        self.assertTrue(any("This book is part of existing orders. Deactivate it instead." in m for m in messages))

        # Test deactivation
        chg_perm = Permission.objects.get(codename="change_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(chg_perm)
        deact_url = reverse("book_deactivate", kwargs={"pk": book.pk})
        res_deact = self.client.post(deact_url, follow=True)
        self.assertEqual(res_deact.status_code, 200)
        book.refresh_from_db()
        self.assertFalse(book.is_active)

    def test_book_add_and_edit(self):
        add_perm = Permission.objects.get(codename="add_book", content_type__app_label="store")
        chg_perm = Permission.objects.get(codename="change_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(add_perm, chg_perm)
        self.client.login(username="staff", password="password123")

        # 1. Add book
        add_url = reverse("book_add")
        res_add = self.client.post(add_url, {
            "title": "A Brand New Test Book",
            "author": "Test Author",
            "category": self.cat_fiction.pk,
            "price": "350.00",
            "old_price": "450.00",
            "description": "Great test book",
            "stock": 15,
            "rating": "4.5",
            "is_best_seller": True,
            "is_new_arrival": True,
            "is_active": True,
        }, follow=True)
        self.assertEqual(res_add.status_code, 200)
        new_book = Book.objects.filter(title="A Brand New Test Book").first()
        self.assertIsNotNone(new_book)
        self.assertEqual(new_book.stock, 15)

        # 2. Edit book
        edit_url = reverse("book_edit", kwargs={"pk": new_book.pk})
        res_edit = self.client.post(edit_url, {
            "title": "A Brand New Test Book (Updated)",
            "author": "Test Author",
            "category": self.cat_fiction.pk,
            "price": "399.00",
            "old_price": "499.00",
            "description": "Updated description",
            "stock": 25,
            "rating": "4.8",
            "is_best_seller": False,
            "is_new_arrival": True,
            "is_active": True,
        }, follow=True)
        self.assertEqual(res_edit.status_code, 200)
        new_book.refresh_from_db()
        self.assertEqual(new_book.title, "A Brand New Test Book (Updated)")
        self.assertEqual(new_book.price, Decimal("399.00"))
        self.assertEqual(new_book.stock, 25)
        messages = [m.message for m in get_messages(res_edit.wsgi_request)]
        self.assertIn("Book updated", messages)

    def test_bulk_delete(self):
        del_perm = Permission.objects.get(codename="delete_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(del_perm)
        self.client.login(username="staff", password="password123")

        b1 = self.books[9]
        b2 = self.books[10]
        bulk_url = reverse("book_bulk_delete")
        res = self.client.post(bulk_url, {"selected_books": [b1.pk, b2.pk]}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Book.objects.filter(pk=b1.pk).exists())
        self.assertFalse(Book.objects.filter(pk=b2.pk).exists())
        messages = [m.message for m in get_messages(res.wsgi_request)]
        self.assertIn("Deleted 2 book(s).", messages)

    def test_dashboard_books_view_and_permissions(self):
        self.client.login(username="staff", password="password123")
        res = self.client.get(reverse("dashboard_books"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("books", res.context)

        # Without delete_book or change_book, action buttons are hidden
        content = res.content.decode("utf-8")
        self.assertNotIn("Delete Selected", content)

        # With delete_book and change_book
        del_perm = Permission.objects.get(codename="delete_book", content_type__app_label="store")
        chg_perm = Permission.objects.get(codename="change_book", content_type__app_label="store")
        add_perm = Permission.objects.get(codename="add_book", content_type__app_label="store")
        self.staff_user.user_permissions.add(del_perm, chg_perm, add_perm)

        res2 = self.client.get(reverse("dashboard_books"))
        content2 = res2.content.decode("utf-8")
        self.assertIn("Delete Selected", content2)
        self.assertIn("Add New Book", content2)

    @patch("requests.get")
    def test_import_books_field_mapping(self, mock_get):
        # 1. Mock API volume response
        api_volume = {
            "volumeInfo": {
                "title": "Mock Architecture Book",
                "authors": ["Alice Smith", "Bob Jones"],
                "description": "<p>A <b>modern</b> guide to software architecture.</p>",
                "publisher": "Tech Press",
                "pageCount": 420,
                "language": "en",
                "averageRating": 4.8,
                "ratingsCount": 1600,
                "publishedDate": "2023-08-15",
                "imageLinks": {
                    "thumbnail": "http://example.com/cover.jpg?zoom=1"
                }
            },
            "saleInfo": {
                "listPrice": {
                    "amount": 599.00,
                    "currencyCode": "INR"
                }
            }
        }

        # Mock requests.get to return API items or image content
        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "INVALID_ID_000" in url:
                mock_resp.status_code = 404
                return mock_resp
            elif "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [api_volume]}
                return mock_resp
            else:
                # Cover image download
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = make_valid_test_jpeg()
                return mock_resp

        mock_get.side_effect = mock_side_effect

        call_command("import_books", per_category=1)

        book = Book.objects.filter(title="Mock Architecture Book").first()
        self.assertIsNotNone(book)
        self.assertEqual(book.author, "Alice Smith, Bob Jones")
        self.assertEqual(book.description, "A modern guide to software architecture.")
        self.assertEqual(book.publisher, "Tech Press")
        self.assertEqual(book.pages, 420)
        self.assertEqual(book.language, "English")
        self.assertEqual(book.rating, 4.8)
        self.assertEqual(book.reviews_count, 1600)
        self.assertEqual(book.price, Decimal("599.00"))
        self.assertTrue(bool(book.cover_image))
        self.assertTrue(book.cover_image.name.endswith(".jpg"))

    @patch("requests.get")
    def test_import_books_duplicate_skipping(self, mock_get):
        # Book already exists
        api_volume = {
            "volumeInfo": {
                "title": "Clean Code",
                "authors": ["Robert C. Martin"],
                "description": "A Handbook of Agile Software Craftsmanship.",
                "publisher": "Prentice Hall",
                "pageCount": 464,
                "language": "en",
                "averageRating": 4.6,
                "ratingsCount": 1200,
                "publishedDate": "2008-08-01",
                "imageLinks": {
                    "thumbnail": "https://example.com/cover.jpg"
                }
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "INVALID_ID_000" in url:
                mock_resp.status_code = 404
                return mock_resp
            elif "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [api_volume]}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = make_valid_test_jpeg()
                return mock_resp

        mock_get.side_effect = mock_side_effect

        initial_count = Book.objects.filter(title="Clean Code").count()
        self.assertEqual(initial_count, 1)

        call_command("import_books", per_category=1)

        # Count must remain 1 (no duplicate created)
        final_count = Book.objects.filter(title="Clean Code").count()
        self.assertEqual(final_count, 1)

    @patch("requests.get")
    def test_import_books_missing_cover_and_fields_skipped(self, mock_get):
        incomplete_volumes = [
            # Missing cover
            {
                "volumeInfo": {
                    "title": "No Cover Book",
                    "authors": ["Author One"],
                    "description": "Has description but no cover",
                }
            },
            # Missing author
            {
                "volumeInfo": {
                    "title": "No Author Book",
                    "description": "Has description and cover",
                    "imageLinks": {"thumbnail": "https://example.com/cover.jpg"}
                }
            },
            # Missing description
            {
                "volumeInfo": {
                    "title": "No Desc Book",
                    "authors": ["Author Three"],
                    "imageLinks": {"thumbnail": "https://example.com/cover.jpg"}
                }
            },
        ]

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": incomplete_volumes}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = b"fake-cover"
                return mock_resp

        mock_get.side_effect = mock_side_effect

        call_command("import_books", per_category=1)

        self.assertFalse(Book.objects.filter(title="No Cover Book").exists())
        self.assertFalse(Book.objects.filter(title="No Author Book").exists())
        self.assertFalse(Book.objects.filter(title="No Desc Book").exists())

    @patch("requests.get")
    def test_import_books_fallback_price_and_rating(self, mock_get):
        volume_no_ratings_or_price = {
            "volumeInfo": {
                "title": "Fallback Logic Book",
                "authors": ["Test Fallback Author"],
                "description": "Detailed book with no ratings or price in volumeInfo.",
                "publishedDate": "2022-01-01",
                "imageLinks": {
                    "thumbnail": "https://example.com/cover.jpg"
                }
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "INVALID_ID_000" in url:
                mock_resp.status_code = 404
                return mock_resp
            elif "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [volume_no_ratings_or_price]}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = make_valid_test_jpeg()
                return mock_resp

        mock_get.side_effect = mock_side_effect

        call_command("import_books", per_category=1)

        book = Book.objects.filter(title="Fallback Logic Book").first()
        self.assertIsNotNone(book)
        self.assertGreaterEqual(book.rating, 3.8)
        self.assertLessEqual(book.rating, 5.0)
        self.assertGreaterEqual(book.reviews_count, 80)
        self.assertLessEqual(book.reviews_count, 2500)
        self.assertGreaterEqual(book.price, Decimal("199.00"))
        self.assertLessEqual(book.price, Decimal("899.00"))
        self.assertIsNotNone(book.old_price)
        self.assertGreater(book.old_price, book.price)
        self.assertGreaterEqual(book.stock, 10)
        self.assertLessEqual(book.stock, 80)

    @patch("requests.get")
    def test_import_books_clear_dummy_protects_orders(self, mock_get):
        # 1. Create a dummy book linked to an order
        dummy_ordered_book = Book.objects.create(
            title="The Midnight Library",
            author="Matt Haig",
            category=self.cat_fiction,
            price=Decimal("359.00"),
            stock=10,
            is_active=True
        )
        order = Order.objects.create(
            name="Bob",
            email="bob@example.com",
            phone="9876543210",
            address_line1="456 Elm St",
            city="City",
            state="State",
            pin="654321",
            total_amount=Decimal("359.00")
        )
        OrderItem.objects.create(
            order=order,
            book=dummy_ordered_book,
            quantity=1,
            price=dummy_ordered_book.price
        )

        # 2. Create another dummy book WITHOUT order
        dummy_unlinked_book = Book.objects.create(
            title="A Brief History of Modern India",
            author="Rajiv Ahir",
            category=self.cat_nonfiction,
            price=Decimal("220.00"),
            stock=10,
            is_active=True
        )

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "INVALID_ID_000" in url:
                mock_resp.status_code = 404
                return mock_resp
            elif "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": []}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = make_valid_test_jpeg()
                return mock_resp

        mock_get.side_effect = mock_side_effect

        # Run with clear_dummy=True
        call_command("import_books", clear_dummy=True, per_category=1)

        # Dummy book without order MUST be deleted
        self.assertFalse(Book.objects.filter(pk=dummy_unlinked_book.pk).exists())

        # Dummy book WITH order MUST NOT be deleted, but deactivated (is_active=False)
        dummy_ordered_book.refresh_from_db()
        self.assertTrue(Book.objects.filter(pk=dummy_ordered_book.pk).exists())
        self.assertFalse(dummy_ordered_book.is_active)

    @patch("requests.get")
    def test_placeholder_hash_detected_and_rejected(self, mock_get):
        placeholder_bytes = make_valid_test_jpeg(200, 250)
        vol = {
            "volumeInfo": {
                "title": "Placeholder Hash Book",
                "authors": ["Author Placeholder"],
                "description": "Book with a placeholder cover hash.",
                "language": "en",
                "imageLinks": {"thumbnail": "https://example.com/placeholder_cover.jpg"},
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "INVALID_ID_000" in url:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = placeholder_bytes
                return mock_resp
            elif "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [vol]}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = placeholder_bytes
                return mock_resp

        mock_get.side_effect = mock_side_effect
        call_command("import_books", per_category=1)
        self.assertFalse(Book.objects.filter(title="Placeholder Hash Book").exists())

    @patch("requests.get")
    def test_tiny_image_rejected(self, mock_get):
        tiny_bytes = make_valid_test_jpeg(100, 100)
        vol = {
            "volumeInfo": {
                "title": "Tiny Cover Book",
                "authors": ["Author Tiny"],
                "description": "Book with dimensions smaller than 150x200.",
                "language": "en",
                "imageLinks": {"thumbnail": "https://example.com/tiny_cover.jpg"},
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [vol]}
                return mock_resp
            else:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = tiny_bytes
                return mock_resp

        mock_get.side_effect = mock_side_effect
        call_command("import_books", per_category=1)
        self.assertFalse(Book.objects.filter(title="Tiny Cover Book").exists())

    @patch("requests.get")
    def test_open_library_fallback_used_when_google_fails(self, mock_get):
        valid_ol_bytes = make_valid_test_jpeg(300, 400)
        vol = {
            "volumeInfo": {
                "title": "Open Library Fallback Book",
                "authors": ["Author Fallback"],
                "description": "Book where Google cover fails but Open Library succeeds.",
                "language": "en",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9781234567890"}
                ],
                "imageLinks": {"thumbnail": "https://example.com/google_fail.jpg"},
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [vol]}
                return mock_resp
            elif "openlibrary.org" in url:
                mock_resp.status_code = 200
                mock_resp.headers = {"Content-Type": "image/jpeg"}
                mock_resp.content = valid_ol_bytes
                return mock_resp
            else:
                mock_resp.status_code = 404
                return mock_resp

        mock_get.side_effect = mock_side_effect
        call_command("import_books", per_category=1)
        book = Book.objects.filter(title="Open Library Fallback Book").first()
        self.assertIsNotNone(book)
        self.assertTrue(bool(book.cover_image))
        self.assertTrue(book.is_active)

    @patch("requests.get")
    def test_book_without_any_valid_cover_skipped(self, mock_get):
        vol = {
            "volumeInfo": {
                "title": "No Valid Cover Book",
                "authors": ["Author None"],
                "description": "Book where both Google and Open Library fail.",
                "language": "en",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9789999999999"}
                ],
                "imageLinks": {"thumbnail": "https://example.com/google_404.jpg"},
            }
        }

        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "googleapis.com" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [vol]}
                return mock_resp
            else:
                mock_resp.status_code = 404
                return mock_resp

        mock_get.side_effect = mock_side_effect
        call_command("import_books", per_category=1)
        self.assertFalse(Book.objects.filter(title="No Valid Cover Book").exists())

    @patch("requests.get")
    def test_clean_covers_keeps_books_with_orders_but_deactivates_them(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake-placeholder-bytes"
        mock_get.return_value = mock_resp

        # 1. Book with missing cover AND orders
        ordered_bad_book = Book.objects.create(
            title="Ordered Bad Book",
            author="Author One",
            category=self.cat_fiction,
            price=Decimal("299.00"),
            cover_image=None,
            is_active=True,
        )
        order = Order.objects.create(
            name="Alice",
            email="alice@example.com",
            phone="9876543210",
            address_line1="123 Test St",
            city="Test City",
            state="Test State",
            pin="123456",
            total_amount=Decimal("299.00"),
        )
        OrderItem.objects.create(
            order=order,
            book=ordered_bad_book,
            quantity=1,
            price=ordered_bad_book.price,
        )

        # 2. Book with missing cover and NO orders
        unlinked_bad_book = Book.objects.create(
            title="Unlinked Bad Book",
            author="Author Two",
            category=self.cat_fiction,
            price=Decimal("199.00"),
            cover_image=None,
            is_active=True,
        )

        call_command("clean_covers")

        # Book without orders should be deleted
        self.assertFalse(Book.objects.filter(pk=unlinked_bad_book.pk).exists())

        # Book with orders must NOT be deleted, but deactivated (is_active=False)
        ordered_bad_book.refresh_from_db()
        self.assertTrue(Book.objects.filter(pk=ordered_bad_book.pk).exists())
        self.assertFalse(ordered_bad_book.is_active)


class CartTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Fiction")
        self.book1 = Book.objects.create(
            title="Book One",
            author="Author One",
            category=self.category,
            price=Decimal("499.00"),
            old_price=Decimal("699.00"),
            stock=10,
            is_active=True,
        )
        self.book2 = Book.objects.create(
            title="Book Two",
            author="Author Two",
            category=self.category,
            price=Decimal("399.00"),
            old_price=Decimal("499.00"),
            stock=10,
            is_active=True,
        )
        self.book3 = Book.objects.create(
            title="Book Three",
            author="Author Three",
            category=self.category,
            price=Decimal("599.00"),
            old_price=None,
            stock=10,
            is_active=True,
        )

    def test_adding_same_book_twice_makes_quantity_two(self):
        # Adding the same book twice makes quantity 2 (not two rows).
        url = reverse("cart_add", args=[self.book1.id])
        self.client.post(url, {"qty": 1})
        self.client.post(url, {"qty": 1})
        session_cart = self.client.session.get("cart", {})
        self.assertEqual(len(session_cart), 1)
        self.assertEqual(session_cart[str(self.book1.id)], 2)

        res = self.client.get(reverse("cart"))
        items = list(res.context["items"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 2)

    def test_adding_two_different_books_shows_both_in_cart_and_checkout(self):
        # Adding two different books shows both in /cart/ and /checkout/.
        self.client.post(reverse("cart_add", args=[self.book1.id]), {"qty": 1})
        self.client.post(reverse("cart_add", args=[self.book2.id]), {"qty": 1})

        cart_res = self.client.get(reverse("cart"))
        self.assertEqual(cart_res.status_code, 200)
        self.assertContains(cart_res, self.book1.title)
        self.assertContains(cart_res, self.book2.title)

        checkout_res = self.client.get(reverse("checkout"))
        self.assertEqual(checkout_res.status_code, 200)
        self.assertContains(checkout_res, self.book1.title)
        self.assertContains(checkout_res, self.book2.title)

    def test_navbar_badge_equals_total_quantity(self):
        # The navbar badge equals the total quantity.
        self.client.post(reverse("cart_add", args=[self.book1.id]), {"qty": 2})
        self.client.post(reverse("cart_add", args=[self.book2.id]), {"qty": 3})

        home_res = self.client.get(reverse("home"))
        self.assertEqual(home_res.context["cart_count"], 5)
        self.assertContains(home_res, '<span class="badge-cart">5</span>')

    def test_subtotal_savings_shipping_and_total_calculations(self):
        # Subtotal, savings, shipping and total are correct (for example 3 books of 499, 399, 599
        # gives subtotal 1497 and shipping 0).
        self.client.post(reverse("cart_add", args=[self.book1.id]), {"qty": 1})
        self.client.post(reverse("cart_add", args=[self.book2.id]), {"qty": 1})
        self.client.post(reverse("cart_add", args=[self.book3.id]), {"qty": 1})

        res = self.client.get(reverse("cart"))
        self.assertEqual(res.context["subtotal"], Decimal("1497.00"))
        # savings: (699-499)*1 + (499-399)*1 = 200 + 100 = 300
        self.assertEqual(res.context["discount"], Decimal("300.00"))
        self.assertEqual(res.context["shipping"], Decimal("0.00"))
        self.assertEqual(res.context["total"], Decimal("1497.00"))

        # Test shipping fee when subtotal < 499
        cheap_book = Book.objects.create(
            title="Cheap Book",
            author="Cheap Author",
            category=self.category,
            price=Decimal("200.00"),
            old_price=Decimal("250.00"),
            stock=10,
            is_active=True,
        )
        cheap_client = Client()
        cheap_client.post(reverse("cart_add", args=[cheap_book.id]), {"qty": 1})
        cheap_res = cheap_client.get(reverse("cart"))
        self.assertEqual(cheap_res.context["subtotal"], Decimal("200.00"))
        self.assertEqual(cheap_res.context["discount"], Decimal("50.00"))
        self.assertEqual(cheap_res.context["shipping"], Decimal("49.00"))
        self.assertEqual(cheap_res.context["total"], Decimal("249.00"))

    def test_remove_and_update_work_quantity_zero_removes_and_stock_respected(self):
        # Remove and update work; quantity 0 removes the item; stock is respected.
        limited_book = Book.objects.create(
            title="Limited Stock Book",
            author="Limited Author",
            category=self.category,
            price=Decimal("250.00"),
            stock=3,
            is_active=True,
        )
        self.client.post(reverse("cart_add", args=[limited_book.id]), {"qty": 1})

        # Update to quantity 2
        self.client.post(reverse("cart_update", args=[limited_book.id]), {"quantity": 2})
        session_cart = self.client.session.get("cart", {})
        self.assertEqual(session_cart[str(limited_book.id)], 2)

        # Update beyond stock (requested 10, stock is 3) -> should clamp to 3
        upd_clamp = self.client.post(reverse("cart_update", args=[limited_book.id]), {"quantity": 10}, follow=True)
        session_cart = self.client.session.get("cart", {})
        self.assertEqual(session_cart[str(limited_book.id)], 3)
        msgs = [m.message for m in get_messages(upd_clamp.wsgi_request)]
        self.assertTrue(any("Only 3 copies in stock" in m for m in msgs))

        # Update to quantity 0 -> removes item
        self.client.post(reverse("cart_update", args=[limited_book.id]), {"quantity": 0})
        session_cart = self.client.session.get("cart", {})
        self.assertNotIn(str(limited_book.id), session_cart)

        # Test cart_remove view explicitly
        self.client.post(reverse("cart_add", args=[limited_book.id]), {"qty": 1})
        rem_res = self.client.post(reverse("cart_remove", args=[limited_book.id]), follow=True)
        session_cart = self.client.session.get("cart", {})
        self.assertNotIn(str(limited_book.id), session_cart)
        msgs = [m.message for m in get_messages(rem_res.wsgi_request)]
        self.assertTrue(any("Book removed from cart" in m for m in msgs))

    def test_inactive_or_deleted_books_are_removed_from_cart_automatically(self):
        # Inactive or deleted books are removed from the cart automatically.
        self.client.post(reverse("cart_add", args=[self.book1.id]), {"qty": 1})
        self.client.post(reverse("cart_add", args=[self.book2.id]), {"qty": 1})

        # Book 1 gets deactivated
        self.book1.is_active = False
        self.book1.save()

        # Book 2 gets deleted
        self.book2.delete()

        # Accessing cart or any page cleans them up automatically
        res = self.client.get(reverse("cart"))
        session_cart = self.client.session.get("cart", {})
        self.assertEqual(session_cart, {})
        self.assertEqual(res.context["cart_total_items"], 0)
        self.assertEqual(res.context["items"], [])

    def test_get_on_cart_add_returns_405(self):
        # GET on cart_add returns 405.
        res = self.client.get(reverse("cart_add", args=[self.book1.id]))
        self.assertEqual(res.status_code, 405)

    def test_empty_cart_redirects_from_checkout_to_cart(self):
        res = self.client.get(reverse("checkout"))
        self.assertRedirects(res, reverse("cart"))




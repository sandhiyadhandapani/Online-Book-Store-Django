from decimal import Decimal
from store.models import Book


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get("cart")
        if cart is None or not isinstance(cart, dict):
            cart = self.session["cart"] = {}
        self.cart = cart
        self._items = None

    def save(self):
        self.session["cart"] = self.cart
        self.session.modified = True
        self._items = None

    def add(self, book_id, qty=1):
        str_id = str(book_id)
        try:
            qty = int(qty)
        except (ValueError, TypeError):
            qty = 1
        if qty < 1:
            qty = 1

        book = Book.objects.filter(pk=book_id, is_active=True).first()
        if not book or book.stock <= 0:
            return 0, False

        current_qty = self.cart.get(str_id, 0)
        target_qty = current_qty + qty
        clamped_qty = min(target_qty, book.stock)
        was_clamped = clamped_qty < target_qty

        self.cart[str_id] = clamped_qty
        self.save()
        return clamped_qty, was_clamped

    def update(self, book_id, qty):
        str_id = str(book_id)
        try:
            qty = int(qty)
        except (ValueError, TypeError):
            qty = 1

        if qty <= 0:
            self.remove(book_id)
            return 0, False

        book = Book.objects.filter(pk=book_id, is_active=True).first()
        if not book or book.stock <= 0:
            self.remove(book_id)
            return 0, False

        clamped_qty = min(qty, book.stock)
        was_clamped = clamped_qty < qty

        self.cart[str_id] = clamped_qty
        self.save()
        return clamped_qty, was_clamped

    def remove(self, book_id):
        str_id = str(book_id)
        if str_id in self.cart:
            del self.cart[str_id]
            self.save()

    def clear(self):
        self.cart = {}
        self.session["cart"] = {}
        self.session.modified = True
        self._items = None

    def _get_items(self):
        if self._items is not None:
            return self._items

        valid_ids = [int(k) for k in self.cart.keys() if str(k).isdigit()]
        active_books = {
            b.id: b
            for b in Book.objects.filter(id__in=valid_ids, is_active=True).select_related("category")
        }

        items = []
        modified = False

        for str_id, raw_qty in list(self.cart.items()):
            try:
                pk = int(str_id)
            except (ValueError, TypeError):
                del self.cart[str_id]
                modified = True
                continue

            book = active_books.get(pk)
            if not book or book.stock <= 0:
                del self.cart[str_id]
                modified = True
                continue

            try:
                qty = int(raw_qty)
            except (ValueError, TypeError):
                qty = 1

            clamped_qty = max(1, min(qty, book.stock))
            if clamped_qty != qty:
                self.cart[str_id] = clamped_qty
                modified = True

            price_dec = Decimal(str(book.price))
            old_price_dec = Decimal(str(book.old_price)) if book.old_price is not None else None
            line_total = price_dec * clamped_qty

            items.append({
                "book": book,
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "price": price_dec,
                "old_price": old_price_dec,
                "cover_image": book.cover_image,
                "c1": book.c1,
                "c2": book.c2,
                "quantity": clamped_qty,
                "line_total": line_total,
                "item_total": line_total,
            })

        if modified:
            self.session["cart"] = self.cart
            self.session.modified = True

        self._items = items
        return self._items

    def __iter__(self):
        for item in self._get_items():
            yield item

    def __len__(self):
        return sum(item["quantity"] for item in self._get_items())

    @property
    def subtotal(self):
        return sum((item["line_total"] for item in self._get_items()), Decimal("0.00"))

    @property
    def total_savings(self):
        savings = Decimal("0.00")
        for item in self._get_items():
            if item["old_price"] and item["old_price"] > item["price"]:
                savings += (item["old_price"] - item["price"]) * item["quantity"]
        return savings

    @property
    def shipping(self):
        if len(self) == 0 or self.subtotal == Decimal("0.00"):
            return Decimal("0.00")
        if self.subtotal >= Decimal("499.00"):
            return Decimal("0.00")
        return Decimal("49.00")

    @property
    def total(self):
        return self.subtotal + self.shipping

from store.cart import Cart


def cart_context(request):
    cart = Cart(request)
    return {
        "cart": cart,
        "cart_count": len(cart),
        "cart_total": cart.total,
    }


def wishlist_context(request):
    if hasattr(request, "user") and request.user.is_authenticated:
        from store.models import Wishlist
        book_ids = set(Wishlist.objects.filter(user=request.user).values_list("book_id", flat=True))
        return {
            "wishlist_book_ids": book_ids,
            "wishlist_count": len(book_ids),
        }
    return {
        "wishlist_book_ids": set(),
        "wishlist_count": 0,
    }

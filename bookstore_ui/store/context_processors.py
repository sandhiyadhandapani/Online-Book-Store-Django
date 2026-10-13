from store.cart import Cart


def cart_context(request):
    cart = Cart(request)
    return {
        "cart": cart,
        "cart_count": len(cart),
        "cart_total": cart.total,
    }

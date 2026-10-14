from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, ProtectedError
from django.http import HttpResponseNotAllowed, HttpResponseForbidden, JsonResponse, Http404
from django.urls import reverse
from .models import Book, Category, Order, OrderItem, Subscriber, UserProfile, Wishlist
from .forms import BookForm, RegisterForm, LoginForm, CheckoutForm, ProfileForm
from .cart import Cart

User = get_user_model()
email_validator = EmailValidator()


def _get_cats():
    categories = Category.objects.annotate(
        book_count=Count("books", filter=Q(books__is_active=True))
    ).order_by("name")
    return [(c.name, c.icon or "bi-book", c.book_count) for c in categories]


def _ctx(**extra):
    return {
        "cats": _get_cats(),
        **extra,
    }


def home(request):
    best = Book.objects.filter(is_best_seller=True, is_active=True).select_related("category")[:4]
    new = Book.objects.filter(is_new_arrival=True, is_active=True).select_related("category")[:4]
    return render(request, "home.html", _ctx(nav="home", best=best, new=new))


def book_list(request):
    books = Book.objects.filter(is_active=True).select_related("category")

    # Categories filter (multiple allowed)
    selected_cats = request.GET.getlist("cat")
    if not selected_cats and request.GET.get("cat"):
        selected_cats = [request.GET.get("cat")]
    if selected_cats:
        books = books.filter(category__name__in=selected_cats)

    # Search keyword filter
    q = request.GET.get("q", "").strip()
    if q:
        books = books.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(category__name__icontains=q)
        )

    # Price range filter
    selected_price = request.GET.get("price", "").strip()
    if selected_price == "0-250":
        books = books.filter(price__lte=250)
    elif selected_price == "250-500":
        books = books.filter(price__gte=250, price__lte=500)
    elif selected_price == "500-1000":
        books = books.filter(price__gte=500, price__lte=1000)
    elif selected_price == "1000-":
        books = books.filter(price__gte=1000)

    # Rating filter
    selected_rating = request.GET.get("rating", "").strip()
    if selected_rating:
        try:
            books = books.filter(rating__gte=float(selected_rating))
        except ValueError:
            pass

    # Sort order
    sort = request.GET.get("sort", "Newest First").strip()
    if sort == "Price: Low to High":
        books = books.order_by("price", "-created_at")
    elif sort == "Price: High to Low":
        books = books.order_by("-price", "-created_at")
    elif sort == "Top Rated":
        books = books.order_by("-rating", "-created_at")
    else:
        sort = "Newest First"
        books = books.order_by("-created_at")

    # Paginate 12 per page
    paginator = Paginator(books, 12)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Preserve all other GET parameters across pagination links
    query_params = request.GET.copy()
    if "page" in query_params:
        del query_params["page"]
    query_string = query_params.urlencode()

    return render(request, "books.html", _ctx(
        nav="books",
        books=page_obj,
        page_obj=page_obj,
        paginator=paginator,
        pages=paginator.page_range,
        query_string=query_string,
        selected_cats=selected_cats,
        selected_price=selected_price,
        selected_rating=selected_rating,
        q=q,
        sort=sort,
    ))


def book_detail(request, pk=1):
    book = get_object_or_404(
        Book.objects.select_related("category"),
        pk=pk,
        is_active=True
    )
    related = Book.objects.filter(
        category=book.category,
        is_active=True
    ).exclude(pk=book.pk).select_related("category")[:4]

    return render(request, "book_detail.html", _ctx(
        nav="books",
        book=book,
        related=related,
    ))


def _redirect_back(request, fallback="cart"):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect(fallback)


def cart_view(request):
    cart = Cart(request)
    items = list(cart)
    stock_error_shown = request.session.pop("stock_error_shown", False)
    if not stock_error_shown:
        for item in items:
            if item.get("exceeds_stock"):
                messages.warning(
                    request,
                    f"Only {item['book'].stock} copies of {item['title']} left. Please update your cart."
                )
    return render(request, "cart.html", _ctx(
        nav="cart",
        items=items,
        cart_total_items=len(cart),
        subtotal=cart.subtotal,
        discount=cart.total_savings,
        shipping=cart.shipping,
        total=cart.total,
    ))


def send_order_confirmation_email(order):
    subject = f"Order Confirmation - {order.order_number}"
    items_list = "\n".join([
        f"- {item.quantity}x {item.book.title} @ Rs. {item.price} = Rs. {item.line_total}"
        for item in order.items.select_related("book")
    ])
    addr_line2 = f"{order.address_line2}\n" if order.address_line2 else ""
    message = (
        f"Dear {order.name},\n\n"
        f"Thank you for your order at BookStore! Your order has been placed successfully.\n\n"
        f"Order Number: {order.order_number}\n"
        f"Order Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Status: {order.status}\n"
        f"Payment Method: {order.payment_method}\n\n"
        f"Delivery Address:\n"
        f"{order.name}\n"
        f"{order.address_line1}\n"
        f"{addr_line2}"
        f"{order.city}, {order.state} - {order.pin}\n"
        f"Phone: {order.phone}\n\n"
        f"Items Ordered:\n{items_list}\n\n"
        f"Subtotal: Rs. {order.subtotal}\n"
        f"Shipping: Rs. {order.shipping_fee}\n"
        f"Total Amount: Rs. {order.total_amount}\n\n"
        f"Happy reading!\n"
        f"The BookStore Team"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "orders@bookstore.com")
    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=[order.email],
        fail_silently=True,
    )


def _get_checkout_initial(user):
    initial = {}
    if user.is_authenticated:
        initial["name"] = f"{user.first_name} {user.last_name}".strip() or user.username
        initial["email"] = user.email

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.phone:
            initial["phone"] = profile.phone
        if profile.address_line1:
            initial["address_line1"] = profile.address_line1
            initial["address_line2"] = profile.address_line2
            initial["city"] = profile.city
            initial["state"] = profile.state
            initial["pin"] = profile.pin

        last_order = Order.objects.filter(user=user).order_by("-created_at").first()
        if last_order:
            if not initial.get("phone"):
                initial["phone"] = last_order.phone
            if not initial.get("address_line1"):
                initial["address_line1"] = last_order.address_line1
                initial["address_line2"] = last_order.address_line2
                initial["city"] = last_order.city
                initial["state"] = last_order.state
                initial["pin"] = last_order.pin
    return initial


@login_required(login_url="login")
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            book_ids = [item["id"] for item in cart]
            insufficient_stock_messages = []

            with transaction.atomic():
                locked_books = {
                    b.id: b
                    for b in Book.objects.select_for_update().filter(id__in=book_ids)
                }

                for item in cart:
                    book = locked_books.get(item["id"])
                    if not book or not book.is_active or book.stock < item["quantity"]:
                        avail = book.stock if (book and book.is_active) else 0
                        insufficient_stock_messages.append(
                            f"Only {avail} copies of {item['title']} left. Please update your cart."
                        )

                if insufficient_stock_messages:
                    for msg in insufficient_stock_messages:
                        messages.error(request, msg)
                    request.session["stock_error_shown"] = True
                    return redirect("cart")


                order = Order.objects.create(
                    user=request.user,
                    name=form.cleaned_data["name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                    address_line1=form.cleaned_data["address_line1"],
                    address_line2=form.cleaned_data["address_line2"],
                    city=form.cleaned_data["city"],
                    state=form.cleaned_data["state"],
                    pin=form.cleaned_data["pin"],
                    payment_method=form.cleaned_data["payment_method"],
                    shipping_fee=cart.shipping,
                    subtotal=cart.subtotal,
                    total_amount=cart.total,
                    status="Pending",
                )

                for item in cart:
                    book = locked_books[item["id"]]
                    OrderItem.objects.create(
                        order=order,
                        book=book,
                        quantity=item["quantity"],
                        price=book.price,
                    )
                    book.stock -= item["quantity"]
                    book.save(update_fields=["stock"])

                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                updated_profile = False
                if not profile.phone and order.phone:
                    profile.phone = order.phone
                    updated_profile = True
                if not profile.address_line1 and order.address_line1:
                    profile.address_line1 = order.address_line1
                    profile.address_line2 = order.address_line2
                    profile.city = order.city
                    profile.state = order.state
                    profile.pin = order.pin
                    updated_profile = True
                if updated_profile:
                    profile.save()

                cart.clear()
                send_order_confirmation_email(order)
                messages.success(request, f"Order #{order.order_number} placed successfully!")
                return redirect("order_success", pk=order.pk)
        else:
            messages.error(request, "Please correct the errors in the checkout form.")
    else:
        initial = _get_checkout_initial(request.user)
        form = CheckoutForm(initial=initial)

    items = list(cart)
    return render(request, "checkout.html", _ctx(
        nav="checkout",
        form=form,
        items=items,
        cart_total_items=len(cart),
        subtotal=cart.subtotal,
        discount=cart.total_savings,
        shipping=cart.shipping,
        total=cart.total,
    ))


@login_required(login_url="login")
def order_success(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__book"),
        pk=pk,
        user=request.user
    )
    return render(request, "order_success.html", _ctx(
        nav="orders",
        order=order,
    ))



def cart_add(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    book = get_object_or_404(Book, pk=pk, is_active=True)
    try:
        qty = int(request.POST.get("qty", request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        qty = 1
    if qty < 1:
        qty = 1

    cart = Cart(request)
    if book.stock <= 0:
        messages.warning(request, "Only 0 copies in stock")
        return _redirect_back(request, fallback="cart")

    clamped_qty, was_clamped = cart.add(book.id, qty=qty)
    if was_clamped:
        messages.warning(request, f"Only {book.stock} copies in stock")
    else:
        messages.success(request, f"{book.title} added to cart")

    return _redirect_back(request, fallback="cart")


def cart_remove(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    cart = Cart(request)
    cart.remove(pk)
    messages.success(request, "Book removed from cart")
    return _redirect_back(request, fallback="cart")


def cart_update(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    book = Book.objects.filter(id=pk, is_active=True).first()
    try:
        qty = int(request.POST.get("quantity", 1))
    except (ValueError, TypeError):
        qty = 1

    cart = Cart(request)
    if qty <= 0:
        cart.remove(pk)
        messages.success(request, "Book removed from cart")
    elif book and book.stock > 0 and qty > book.stock:
        cart.update(pk, book.stock)
        messages.warning(request, f"Only {book.stock} copies in stock")
    elif not book or (book and book.stock <= 0):
        cart.remove(pk)
        messages.warning(request, "Only 0 copies in stock")
    else:
        cart.update(pk, qty)
        messages.success(request, "Cart updated")

    return _redirect_back(request, fallback="cart")


def newsletter(request):
    if request.method == "POST":
        raw_email = request.POST.get("email", "")
        email = raw_email.strip().lower()

        if not email:
            messages.error(request, "Enter a valid email address.")
        else:
            try:
                email_validator(email)
            except ValidationError:
                messages.error(request, "Enter a valid email address.")
            else:
                subscriber, created = Subscriber.objects.get_or_create(
                    email=email,
                    defaults={"is_active": True}
                )
                if created:
                    messages.success(request, "Thanks for subscribing!")
                else:
                    if not subscriber.is_active:
                        subscriber.is_active = True
                        subscriber.save()
                        messages.success(request, "Thanks for subscribing!")
                    else:
                        messages.info(request, "You are already subscribed.")

        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("newsletter")

    return render(request, "newsletter.html", _ctx(nav="news"))


@staff_member_required(login_url="/admin/login/")
def dashboard(request):
    total_books = Book.objects.count()
    total_orders = Order.objects.count()
    total_subscribers = Subscriber.objects.count()
    total_users = User.objects.count()
    recent_books = Book.objects.select_related("category").order_by("-created_at")[:5]
    recent_subs = Subscriber.objects.order_by("-subscribed_at")[:4]

    return render(request, "dashboard.html", _ctx(
        nav="dashboard",
        books=recent_books,
        subs=recent_subs,
        total_books=total_books,
        total_orders=total_orders,
        total_subscribers=total_subscribers,
        total_users=total_users,
    ))


@staff_member_required(login_url="/admin/login/")
def dashboard_books(request):
    books_qs = Book.objects.select_related("category").all().order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        books_qs = books_qs.filter(Q(title__icontains=q) | Q(author__icontains=q))

    cat_id = request.GET.get("cat", "").strip()
    if cat_id:
        books_qs = books_qs.filter(category_id=cat_id)

    paginator = Paginator(books_qs, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all().order_by("name")

    # Preserve deactivation candidate from delete attempt if any
    deactivate_candidate_id = request.session.pop("deactivate_candidate_id", None)
    deactivate_candidate_title = request.session.pop("deactivate_candidate_title", None)

    return render(request, "dashboard_books.html", _ctx(
        nav="books",
        books=page_obj,
        page_obj=page_obj,
        paginator=paginator,
        categories=categories,
        q=q,
        cat=cat_id,
        total_count=books_qs.count(),
        deactivate_candidate_id=deactivate_candidate_id,
        deactivate_candidate_title=deactivate_candidate_title,
    ))


@staff_member_required(login_url="/admin/login/")
def book_add(request):
    if not request.user.has_perm("store.add_book"):
        return HttpResponseForbidden("You do not have permission to add books.")

    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
            messages.success(request, f'Book "{book.title}" added successfully.')
            return redirect("dashboard_books")
    else:
        form = BookForm()

    return render(request, "dashboard_book_form.html", _ctx(
        nav="books",
        form=form,
        action="add",
    ))


@staff_member_required(login_url="/admin/login/")
def book_edit(request, pk):
    if not request.user.has_perm("store.change_book"):
        return HttpResponseForbidden("You do not have permission to edit books.")

    book = get_object_or_404(Book, pk=pk)

    if request.method == "POST":
        form = BookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, "Book updated")
            return redirect("dashboard_books")
    else:
        form = BookForm(instance=book)

    return render(request, "dashboard_book_form.html", _ctx(
        nav="books",
        form=form,
        book=book,
        action="edit",
    ))


@staff_member_required(login_url="/admin/login/")
def book_delete(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.has_perm("store.delete_book"):
        return HttpResponseForbidden("You do not have permission to delete books.")

    book = get_object_or_404(Book, pk=pk)

    try:
        if book.order_items.exists():
            messages.error(
                request,
                "This book is part of existing orders. Deactivate it instead."
            )
            request.session["deactivate_candidate_id"] = book.id
            request.session["deactivate_candidate_title"] = book.title
            return redirect("dashboard_books")

        book.delete()
        messages.success(request, "Book deleted")
    except ProtectedError:
        messages.error(
            request,
            "This book is part of existing orders. Deactivate it instead."
        )
        request.session["deactivate_candidate_id"] = book.id
        request.session["deactivate_candidate_title"] = book.title

    return redirect("dashboard_books")


@staff_member_required(login_url="/admin/login/")
def book_deactivate(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.has_perm("store.change_book"):
        return HttpResponseForbidden("You do not have permission to edit books.")

    book = get_object_or_404(Book, pk=pk)
    book.is_active = False
    book.save(update_fields=["is_active"])
    messages.success(request, f'Book "{book.title}" deactivated.')

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("dashboard_books")


@staff_member_required(login_url="/admin/login/")
def book_bulk_delete(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.has_perm("store.delete_book"):
        return HttpResponseForbidden("You do not have permission to delete books.")

    selected_ids = request.POST.getlist("selected_books")
    if not selected_ids:
        messages.warning(request, "No books selected.")
        return redirect("dashboard_books")

    deleted_count = 0
    protected_titles = []

    for book_id in selected_ids:
        book = Book.objects.filter(id=book_id).first()
        if not book:
            continue
        try:
            if book.order_items.exists():
                protected_titles.append(book.title)
                continue
            book.delete()
            deleted_count += 1
        except ProtectedError:
            protected_titles.append(book.title)

    if deleted_count:
        messages.success(request, f"Deleted {deleted_count} book(s).")
    if protected_titles:
        messages.error(
            request,
            f"The following book(s) are part of existing orders and could not be deleted: {', '.join(protected_titles)}. Deactivate them instead."
        )

    return redirect("dashboard_books")


# ==============================================================================
# TEAM 3: AUTH VIEWS
# ==============================================================================

def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            cart_data = request.session.get("cart")
            user = form.save()
            login(request, user)
            if cart_data:
                request.session["cart"] = cart_data
                request.session.modified = True

            messages.success(request, f"Welcome to BookStore, {user.first_name}!")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect("home")
        else:
            messages.error(request, "Please correct the errors in the registration form.")
    else:
        form = RegisterForm()

    return render(request, "register.html", _ctx(
        nav="register",
        form=form,
        next=next_url,
    ))


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            cart_data = request.session.get("cart")
            user = form.get_user()
            login(request, user)
            if cart_data:
                request.session["cart"] = cart_data
                request.session.modified = True

            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect("home")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm(request)

    return render(request, "login.html", _ctx(
        nav="login",
        form=form,
        next=next_url,
    ))


def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


# ==============================================================================
# TEAM 3: MY ACCOUNT & ORDERS
# ==============================================================================

@login_required(login_url="login")
def account_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.first_name = form.cleaned_data["first_name"].strip()
            request.user.last_name = form.cleaned_data["last_name"].strip()
            request.user.email = form.cleaned_data["email"].strip().lower()
            request.user.save(update_fields=["first_name", "last_name", "email"])

            profile.phone = form.cleaned_data["phone"].strip()
            profile.address_line1 = form.cleaned_data["address_line1"].strip()
            profile.address_line2 = form.cleaned_data["address_line2"].strip()
            profile.city = form.cleaned_data["city"].strip()
            profile.state = form.cleaned_data["state"].strip()
            profile.pin = form.cleaned_data["pin"].strip()
            profile.save()

            messages.success(request, "Your profile has been updated successfully.")
            return redirect("account")
        else:
            messages.error(request, "Please correct the errors in the profile form.")
    else:
        initial = {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
            "phone": profile.phone,
            "address_line1": profile.address_line1,
            "address_line2": profile.address_line2,
            "city": profile.city,
            "state": profile.state,
            "pin": profile.pin,
        }
        form = ProfileForm(initial=initial, user=request.user)

    recent_orders = Order.objects.filter(user=request.user).order_by("-created_at")[:4]
    return render(request, "account.html", _ctx(
        nav="account",
        form=form,
        profile=profile,
        recent_orders=recent_orders,
    ))


@login_required(login_url="login")
def order_list(request):
    orders_qs = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
    paginator = Paginator(orders_qs, 10)
    page_number = request.GET.get("page", 1)
    try:
        orders = paginator.page(page_number)
    except PageNotAnInteger:
        orders = paginator.page(1)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)

    return render(request, "order_list.html", _ctx(
        nav="orders",
        orders=orders,
        page_obj=orders,
        paginator=paginator,
    ))


@login_required(login_url="login")
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__book"),
        pk=pk,
        user=request.user
    )
    return render(request, "order_detail.html", _ctx(
        nav="orders",
        order=order,
    ))


@login_required(login_url="login")
def order_cancel(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status != "Pending":
        messages.error(
            request,
            f"Order #{order.order_number or order.id} cannot be cancelled because it is already {order.status}."
        )
        return redirect("order_detail", pk=order.pk)

    with transaction.atomic():
        for item in order.items.select_related("book"):
            book = Book.objects.select_for_update().get(pk=item.book_id)
            book.stock += item.quantity
            book.save(update_fields=["stock"])

        order.status = "Cancelled"
        order.save(update_fields=["status"])

    messages.success(request, f"Order #{order.order_number or order.id} has been cancelled and stock has been restored.")
    return redirect("order_detail", pk=order.pk)


# ==============================================================================
# TEAM 3: WISHLIST VIEWS
# ==============================================================================

def wishlist_toggle(request, book_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    if not request.user.is_authenticated:
        login_url = f"{reverse('login')}?next={request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('books')}"
        if is_ajax:
            return JsonResponse({"error": "login_required", "login_url": login_url}, status=401)
        return redirect(login_url)

    book = get_object_or_404(Book, pk=book_id, is_active=True)
    wishlist_item = Wishlist.objects.filter(user=request.user, book=book).first()

    if wishlist_item:
        wishlist_item.delete()
        added = False
        messages.success(request, f'"{book.title}" removed from your wishlist.')
    else:
        Wishlist.objects.create(user=request.user, book=book)
        added = True
        messages.success(request, f'"{book.title}" added to your wishlist.')

    count = Wishlist.objects.filter(user=request.user).count()

    if is_ajax:
        return JsonResponse({
            "added": added,
            "book_id": book.id,
            "count": count,
            "message": f'"{book.title}" {"added to" if added else "removed from"} your wishlist.'
        })

    return _redirect_back(request, fallback="wishlist")


@login_required(login_url="login")
def wishlist_view(request):
    items = Wishlist.objects.filter(user=request.user).select_related("book__category").order_by("-created_at")
    return render(request, "wishlist.html", _ctx(
        nav="wishlist",
        items=items,
        wishlist_count=items.count(),
    ))



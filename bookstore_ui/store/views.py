from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, ProtectedError
from django.http import HttpResponseNotAllowed, HttpResponseForbidden
from .models import Book, Category, Order, Subscriber
from .forms import BookForm
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
    return render(request, "cart.html", _ctx(
        nav="cart",
        items=items,
        cart_total_items=len(cart),
        subtotal=cart.subtotal,
        discount=cart.total_savings,
        shipping=cart.shipping,
        total=cart.total,
    ))


def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart")

    items = list(cart)
    return render(request, "checkout.html", _ctx(
        nav="checkout",
        items=items,
        cart_total_items=len(cart),
        subtotal=cart.subtotal,
        discount=cart.total_savings,
        shipping=cart.shipping,
        total=cart.total,
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


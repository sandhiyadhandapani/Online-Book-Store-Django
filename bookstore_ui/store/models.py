import datetime
import random
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

COVER_PALETTES = [
    ("#f3c98b", "#e59a3c"),
    ("#1b2f5c", "#e8892b"),
    ("#10253f", "#3e8fd1"),
    ("#2e6b57", "#f4e3c1"),
    ("#f08fb0", "#f6c3d4"),
    ("#5a2d2a", "#c18a3a"),
    ("#1f4c8f", "#e9a13b"),
    ("#2a2f6b", "#8e5bd0"),
    ("#2d5a27", "#88b04b"),
    ("#6a1b9a", "#ab47bc"),
]


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Bootstrap icon class e.g. bi-book")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "category"
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    author = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="books")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    rating = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )
    reviews_count = models.PositiveIntegerField(default=0)
    publisher = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=50, default="English", blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True)
    cover_image = models.ImageField(upload_to="covers/", null=True, blank=True)
    cover_color1 = models.CharField(max_length=20, blank=True)
    cover_color2 = models.CharField(max_length=20, blank=True)
    stock = models.PositiveIntegerField(default=0)
    is_best_seller = models.BooleanField(default=False, db_index=True)
    is_new_arrival = models.BooleanField(default=False, db_index=True)
    is_audiobook = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["is_best_seller"]),
            models.Index(fields=["is_new_arrival"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "book"
            slug = base_slug
            counter = 1
            while Book.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round(((self.old_price - self.price) / self.old_price) * 100)
        return 0

    @property
    def pct(self):
        return round((self.rating / 5.0) * 100, 1) if self.rating else 0.0

    @property
    def reviews(self):
        return self.reviews_count

    @property
    def c1(self):
        if self.cover_color1:
            return self.cover_color1
        palette = COVER_PALETTES[(self.id or 0) % len(COVER_PALETTES)]
        return palette[0]

    @property
    def c2(self):
        if self.cover_color2:
            return self.cover_color2
        palette = COVER_PALETTES[(self.id or 0) % len(COVER_PALETTES)]
        return palette[1]

    def __str__(self):
        return self.title


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-subscribed_at"]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


def generate_order_number():
    date_str = timezone.now().strftime("%Y%m%d")
    prefix = f"BS-{date_str}-"
    try:
        last_order = Order.objects.filter(order_number__startswith=prefix).order_by("-id").first()
        if last_order and last_order.order_number:
            try:
                seq_part = last_order.order_number.split("-")[-1]
                new_seq = int(seq_part) + 1
            except (ValueError, IndexError):
                new_seq = 1
        else:
            new_seq = 1

        candidate = f"{prefix}{new_seq:04d}"
        while Order.objects.filter(order_number=candidate).exists():
            new_seq += 1
            candidate = f"{prefix}{new_seq:04d}"
        return candidate
    except Exception:
        return f"{prefix}{random.randint(1000, 9999):04d}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Confirmed", "Confirmed"),
        ("Shipped", "Shipped"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pin = models.CharField(max_length=20)
    payment_method = models.CharField(max_length=50, default="Cash on Delivery")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = generate_order_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.order_number or self.id} - {self.name}"

    @property
    def line1(self):
        return self.address_line1

    @line1.setter
    def line1(self, value):
        self.address_line1 = value

    @property
    def line2(self):
        return self.address_line2

    @line2.setter
    def line2(self, value):
        self.address_line2 = value


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.book.title} (Order #{self.order.order_number or self.order.id})"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=20, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pin = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "book")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.book.title}"


import csv
from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponse
from django.utils.html import format_html
from .models import Category, Book, Subscriber, Order, OrderItem
from .ai import generate_book_summary, AISummaryError

# Customize Admin Site Headers
admin.site.site_header = "BookStore Admin"
admin.site.site_title = "BookStore Admin"
admin.site.index_title = "BookStore Administration"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_book_count=Count("books"))

    @admin.display(description="Book Count", ordering="_book_count")
    def book_count(self, obj):
        return getattr(obj, "_book_count", obj.books.count())


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "cover_thumbnail",
        "title",
        "author",
        "category",
        "price",
        "stock",
        "is_best_seller",
        "is_new_arrival",
        "is_active",
    )
    list_display_links = ("cover_thumbnail", "title")
    list_filter = (
        "category",
        "is_best_seller",
        "is_new_arrival",
        "is_audiobook",
        "is_active",
    )
    search_fields = ("title", "author")
    list_editable = (
        "price",
        "stock",
        "is_best_seller",
        "is_new_arrival",
        "is_active",
    )
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("cover_preview", "created_at", "updated_at", "ai_summary_updated")
    ordering = ("-created_at",)

    fieldsets = (
        ("Basic Info", {
            "fields": ("title", "slug", "author", "description", "category")
        }),
        ("Pricing", {
            "fields": ("price", "old_price")
        }),
        ("Details", {
            "fields": (
                "publisher",
                "language",
                "pages",
                "cover_image",
                "cover_preview",
                "cover_color1",
                "cover_color2",
                "stock",
                "rating",
                "reviews_count",
            )
        }),
        ("Featured Sections", {
            "fields": ("is_best_seller", "is_new_arrival", "is_audiobook")
        }),
        ("AI Summary", {
            "fields": ("ai_summary", "ai_summary_updated")
        }),
        ("Status", {
            "fields": ("is_active", "created_at", "updated_at")
        }),
    )

    actions = [
        "make_best_seller",
        "remove_best_seller",
        "make_new_arrival",
        "remove_new_arrival",
        "activate_books",
        "deactivate_books",
        "clear_ai_summary",
        "generate_ai_summary",
    ]

    @admin.display(description="Cover")
    def cover_thumbnail(self, obj):
        if obj.cover_image:
            return format_html(
                '<img src="{}" style="width:36px;height:50px;object-fit:cover;border-radius:4px;" alt="{}">',
                obj.cover_image.url,
                obj.title
            )
        return format_html(
            '<div style="width:36px;height:50px;background:linear-gradient(135deg, {}, {});border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:7px;color:#fff;text-align:center;padding:2px;font-weight:600;box-sizing:border-box;">{}</div>',
            obj.c1,
            obj.c2,
            obj.title[:8]
        )

    @admin.display(description="Cover Preview")
    def cover_preview(self, obj):
        if obj.cover_image:
            return format_html(
                '<img src="{}" style="max-height:180px;max-width:140px;object-fit:cover;border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,0.15);" alt="{}">',
                obj.cover_image.url,
                obj.title
            )
        return format_html(
            '<div style="width:120px;height:160px;background:linear-gradient(135deg, {}, {});border-radius:6px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;text-align:center;padding:10px;font-weight:bold;box-sizing:border-box;"><span>{}</span><small style="font-weight:normal;font-size:11px;margin-top:4px;">{}</small></div>',
            obj.c1,
            obj.c2,
            obj.title,
            obj.author
        )

    @admin.action(description="Mark as Best Seller")
    def make_best_seller(self, request, queryset):
        updated = queryset.update(is_best_seller=True)
        self.message_user(request, f"{updated} book(s) marked as Best Seller.")

    @admin.action(description="Remove from Best Sellers")
    def remove_best_seller(self, request, queryset):
        updated = queryset.update(is_best_seller=False)
        self.message_user(request, f"{updated} book(s) removed from Best Sellers.")

    @admin.action(description="Mark as New Arrival")
    def make_new_arrival(self, request, queryset):
        updated = queryset.update(is_new_arrival=True)
        self.message_user(request, f"{updated} book(s) marked as New Arrival.")

    @admin.action(description="Remove from New Arrivals")
    def remove_new_arrival(self, request, queryset):
        updated = queryset.update(is_new_arrival=False)
        self.message_user(request, f"{updated} book(s) removed from New Arrivals.")

    @admin.action(description="Activate")
    def activate_books(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} book(s) activated.")

    @admin.action(description="Deactivate")
    def deactivate_books(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} book(s) deactivated.")

    @admin.action(description="Clear AI summary")
    def clear_ai_summary(self, request, queryset):
        updated = queryset.update(ai_summary="", ai_summary_updated=None)
        self.message_user(request, f"Cleared AI summary for {updated} book(s).")

    @admin.action(description="Generate AI summary")
    def generate_ai_summary(self, request, queryset):
        if queryset.count() > 10:
            self.message_user(
                request,
                "Please select at most 10 books at once for AI summary generation.",
                level=messages.WARNING
            )
            return

        success_count = 0
        for book in queryset:
            try:
                generate_book_summary(book, save=True)
                success_count += 1
            except AISummaryError as e:
                self.message_user(
                    request,
                    f"Failed to generate summary for '{book.title}': {e}",
                    level=messages.ERROR
                )
            except Exception:
                self.message_user(
                    request,
                    f"Unexpected error generating summary for '{book.title}'.",
                    level=messages.ERROR
                )

        if success_count:
            self.message_user(
                request,
                f"Successfully generated AI summary for {success_count} book(s)."
            )


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "subscribed_at", "is_active")
    search_fields = ("email",)
    list_filter = ("is_active",)
    date_hierarchy = "subscribed_at"
    actions = ["export_emails_csv"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Export selected emails as CSV")
    def export_emails_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(["Email", "Subscribed At", "Is Active"])
        for sub in queryset:
            writer.writerow([
                sub.email,
                sub.subscribed_at.strftime("%Y-%m-%d %H:%M:%S"),
                sub.is_active
            ])
        return response


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("book", "quantity", "price")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "total_amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "email", "phone")
    list_editable = ("status",)
    inlines = [OrderItemInline]

    def has_add_permission(self, request):
        return False

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from store.models import Book, Category, Order, Subscriber


class Command(BaseCommand):
    help = "Sets up Catalog Manager and Support Staff role groups and their permissions."

    def handle(self, *args, **options):
        # 1. Catalog Manager
        catalog_manager_group, _ = Group.objects.get_or_create(name="Catalog Manager")
        catalog_perms_codenames = [
            # Book: add, change, delete, view
            "add_book", "change_book", "delete_book", "view_book",
            # Category: add, change, delete, view
            "add_category", "change_category", "delete_category", "view_category",
            # Order: view-only
            "view_order",
        ]
        catalog_perms = Permission.objects.filter(
            content_type__app_label="store",
            codename__in=catalog_perms_codenames
        )
        catalog_manager_group.permissions.set(catalog_perms)
        self.stdout.write(self.style.SUCCESS(
            f"Catalog Manager group configured with {catalog_perms.count()} permissions."
        ))

        # 2. Support Staff
        support_staff_group, _ = Group.objects.get_or_create(name="Support Staff")
        support_perms_codenames = [
            # Order: view, change
            "view_order", "change_order",
            # Subscriber: view-only
            "view_subscriber",
            # Book: view-only
            "view_book",
        ]
        support_perms = Permission.objects.filter(
            content_type__app_label="store",
            codename__in=support_perms_codenames
        )
        support_staff_group.permissions.set(support_perms)
        self.stdout.write(self.style.SUCCESS(
            f"Support Staff group configured with {support_perms.count()} permissions."
        ))

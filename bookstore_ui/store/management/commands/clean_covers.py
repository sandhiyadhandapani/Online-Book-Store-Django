import hashlib
import os
from collections import Counter

import requests
from django.core.management.base import BaseCommand
from PIL import Image

from store.models import Book


GOOGLE_PLACEHOLDER_URL = (
    "https://books.google.com/books/content?id=INVALID_ID_000&printType=books&img=1&zoom=1"
)


class Command(BaseCommand):
    help = "Cleans up books with missing or placeholder covers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate cleanup without deleting books or modifying database.",
        )

    def get_google_placeholder_hash(self):
        """Fetch Google's placeholder image at runtime and return its SHA-256 hash."""
        try:
            resp = requests.get(
                GOOGLE_PLACEHOLDER_URL,
                headers={"User-Agent": "BookstoreImporter/1.0"},
                timeout=10,
            )
            if resp.status_code == 200 and resp.content:
                placeholder_hash = hashlib.sha256(resp.content).hexdigest()
                self.stdout.write(f"Google placeholder hash: {placeholder_hash}")
                return placeholder_hash
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Google placeholder returned HTTP {resp.status_code}"
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Failed to fetch Google placeholder hash: {e}")
            )
        return None

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        if dry_run:
            self.stdout.write(self.style.WARNING("=== RUNNING IN DRY-RUN MODE ==="))

        google_placeholder_hash = self.get_google_placeholder_hash()

        all_books = list(Book.objects.all())
        total_checked = len(all_books)

        # First pass: inspect files and collect hashes
        book_info = {}
        hash_counter = Counter()

        for book in all_books:
            # Check condition (a): empty cover_image or file missing on disk
            if not book.cover_image or not book.cover_image.name:
                book_info[book.id] = {
                    "is_bad": True,
                    "reason": "cover_image is empty",
                    "hash": None,
                    "file_path": None,
                }
                continue

            try:
                file_path = book.cover_image.path
            except (ValueError, NotImplementedError):
                book_info[book.id] = {
                    "is_bad": True,
                    "reason": "cover_image path cannot be resolved",
                    "hash": None,
                    "file_path": None,
                }
                continue

            if not os.path.exists(file_path):
                book_info[book.id] = {
                    "is_bad": True,
                    "reason": "cover_image file does not exist on disk",
                    "hash": None,
                    "file_path": file_path,
                }
                continue

            # File exists on disk, read content and compute SHA-256
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()
            except Exception as e:
                book_info[book.id] = {
                    "is_bad": True,
                    "reason": f"cannot read cover file ({e})",
                    "hash": None,
                    "file_path": file_path,
                }
                continue

            # Check condition (b): Pillow can open and width >= 150, height >= 200
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
                    if width < 150 or height < 200:
                        book_info[book.id] = {
                            "is_bad": True,
                            "reason": f"image dimensions ({width}x{height}) < 150x200",
                            "hash": file_hash,
                            "file_path": file_path,
                        }
                        hash_counter[file_hash] += 1
                        continue
            except Exception as e:
                book_info[book.id] = {
                    "is_bad": True,
                    "reason": f"Pillow cannot open cover file ({e})",
                    "hash": file_hash,
                    "file_path": file_path,
                }
                hash_counter[file_hash] += 1
                continue

            # Record hash for condition (c) check
            book_info[book.id] = {
                "is_bad": False,
                "reason": None,
                "hash": file_hash,
                "file_path": file_path,
            }
            hash_counter[file_hash] += 1

        # Second pass: evaluate condition (c) - Google placeholder hash or shared by 3+ books
        deleted_count = 0
        deactivated_count = 0
        kept_count = 0

        for book in all_books:
            info = book_info[book.id]
            is_bad = info["is_bad"]
            reason = info["reason"]
            file_hash = info["hash"]
            file_path = info["file_path"]

            if not is_bad:
                if google_placeholder_hash and file_hash == google_placeholder_hash:
                    is_bad = True
                    reason = "SHA-256 matches Google placeholder hash"
                elif file_hash and hash_counter[file_hash] >= 3:
                    is_bad = True
                    reason = f"cover SHA-256 shared with {hash_counter[file_hash]} books (placeholder)"

            if is_bad:
                has_orders = book.order_items.exists()
                if has_orders:
                    deactivated_count += 1
                    warning_msg = (
                        f"Warning: Cannot delete '{book.title}' (ID {book.id}) "
                        f"because it has order items. Deactivated instead. [Reason: {reason}]"
                    )
                    self.stdout.write(self.style.WARNING(warning_msg))
                    if not dry_run:
                        book.is_active = False
                        book.save(update_fields=["is_active"])
                else:
                    deleted_count += 1
                    msg_prefix = "[DRY-RUN] Would delete" if dry_run else "Deleted"
                    self.stdout.write(
                        f"  {msg_prefix}: '{book.title}' (ID {book.id}) [Reason: {reason}]"
                    )
                    if not dry_run:
                        book.delete()
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass
            else:
                kept_count += 1

        self.stdout.write("\n" + "=" * 45)
        self.stdout.write("CLEAN COVERS SUMMARY")
        self.stdout.write("=" * 45)
        self.stdout.write(f"checked: {total_checked}")
        self.stdout.write(f"kept: {kept_count}")
        self.stdout.write(f"deleted: {deleted_count}")
        self.stdout.write(f"deactivated: {deactivated_count}")
        self.stdout.write("=" * 45 + "\n")

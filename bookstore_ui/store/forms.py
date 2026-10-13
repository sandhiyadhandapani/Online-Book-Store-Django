from django import forms
from .models import Book, Category


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "category",
            "price",
            "old_price",
            "description",
            "stock",
            "rating",
            "cover_image",
            "is_best_seller",
            "is_new_arrival",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter book title",
                "required": True,
            }),
            "author": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter author name",
                "required": True,
            }),
            "category": forms.Select(attrs={
                "class": "form-select",
                "required": True,
            }),
            "price": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00",
                "required": True,
            }),
            "old_price": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00 (optional)",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Enter book description or summary...",
            }),
            "stock": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "placeholder": "0",
            }),
            "rating": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.1",
                "min": "0",
                "max": "5",
                "placeholder": "0.0 - 5.0",
            }),
            "cover_image": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
            "is_best_seller": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "is_new_arrival": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise forms.ValidationError("Price must be greater than or equal to 0.")
        return price

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating is not None and (rating < 0 or rating > 5):
            raise forms.ValidationError("Rating must be between 0.0 and 5.0.")
        return rating

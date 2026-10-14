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


import re
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError

User = get_user_model()


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "First name", "autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Last name", "autocomplete": "family-name"})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "field", "placeholder": "Email address", "autocomplete": "email"})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
        widgets = {
            "username": forms.TextInput(attrs={"class": "field", "placeholder": "Choose a username", "autocomplete": "username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password" in self.fields:
            self.fields["password"].widget.attrs.update({"class": "field"})
        if "password_confirm" in self.fields:
            self.fields["password_confirm"].widget.attrs.update({"class": "field"})
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.update({"class": "field", "placeholder": "Password"})
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update({"class": "field", "placeholder": "Confirm password"})

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError("Email is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "field",
            "placeholder": "Enter your username",
            "autocomplete": "username",
        })
        self.fields["password"].widget.attrs.update({
            "class": "field",
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        })


PAYMENT_CHOICES = [
    ("Cash on Delivery", "Cash on Delivery (COD)"),
    ("UPI", "UPI (Google Pay, PhonePe, Paytm)"),
    ("Card", "Credit / Debit Card (Demo)"),
]


class CheckoutForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Full Name", "id": "id_name"})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "field", "placeholder": "Email Address", "id": "id_email"})
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "10-digit Phone Number", "id": "id_phone"})
    )
    address_line1 = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "House No., Street / Road", "id": "id_address_line1"})
    )
    address_line2 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Apartment, landmark (optional)", "id": "id_address_line2"})
    )
    city = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "City", "id": "id_city"})
    )
    state = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "State", "id": "id_state"})
    )
    pin = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "6-digit PIN code", "id": "id_pin"})
    )
    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        initial="Cash on Delivery",
        required=True,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"})
    )

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "").strip()
        cleaned = re.sub(r"[\s\-]", "", raw)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = cleaned[1:]

        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValidationError("Enter a valid 10-digit Indian phone number.")
        return cleaned

    def clean_pin(self):
        pin = self.cleaned_data.get("pin", "").strip()
        if not re.match(r"^[1-9]\d{5}$", pin):
            raise ValidationError("Enter a valid 6-digit Indian PIN code.")
        return pin


class ProfileForm(forms.Form):
    first_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "First name"})
    )
    last_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Last name"})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "field", "placeholder": "Email address"})
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "10-digit mobile number"})
    )
    address_line1 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Address line 1"})
    )
    address_line2 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "Address line 2 (optional)"})
    )
    city = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "City"})
    )
    state = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "State"})
    )
    pin = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={"class": "field", "placeholder": "6-digit PIN code"})
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError("Email is required.")
        if self.user and User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise ValidationError("This email is already in use by another account.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "").strip()
        if not raw:
            return ""
        cleaned = re.sub(r"[\s\-]", "", raw)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = cleaned[1:]
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValidationError("Enter a valid 10-digit Indian phone number.")
        return cleaned

    def clean_pin(self):
        pin = self.cleaned_data.get("pin", "").strip()
        if not pin:
            return ""
        if not re.match(r"^[1-9]\d{5}$", pin):
            raise ValidationError("Enter a valid 6-digit PIN code.")
        return pin


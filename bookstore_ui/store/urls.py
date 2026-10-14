from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('books/', views.book_list, name='books'),
    path('books/<int:pk>/', views.book_detail, name='book_detail'),
    path('cart/', views.cart_view, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('cart/remove/<int:pk>/', views.cart_remove, name='cart_remove'),
    path('cart/update/<int:pk>/', views.cart_update, name='cart_update'),
    path('cart/add/<int:pk>/', views.cart_add, name='cart_add'),
    path('newsletter/', views.newsletter, name='newsletter'),

    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Orders & Checkout
    path('orders/<int:pk>/success/', views.order_success, name='order_success'),
    path('orders/', views.order_list, name='orders'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/cancel/', views.order_cancel, name='order_cancel'),

    # Account & Wishlist
    path('account/', views.account_view, name='account'),
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/toggle/<int:book_id>/', views.wishlist_toggle, name='wishlist_toggle'),

    # Admin Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/books/', views.dashboard_books, name='dashboard_books'),
    path('dashboard/books/add/', views.book_add, name='book_add'),
    path('dashboard/books/<int:pk>/edit/', views.book_edit, name='book_edit'),
    path('dashboard/books/<int:pk>/delete/', views.book_delete, name='book_delete'),
    path('dashboard/books/<int:pk>/deactivate/', views.book_deactivate, name='book_deactivate'),
    path('dashboard/books/bulk-delete/', views.book_bulk_delete, name='book_bulk_delete'),
]

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
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/books/', views.dashboard_books, name='dashboard_books'),
    path('dashboard/books/add/', views.book_add, name='book_add'),
    path('dashboard/books/<int:pk>/edit/', views.book_edit, name='book_edit'),
    path('dashboard/books/<int:pk>/delete/', views.book_delete, name='book_delete'),
    path('dashboard/books/<int:pk>/deactivate/', views.book_deactivate, name='book_deactivate'),
    path('dashboard/books/bulk-delete/', views.book_bulk_delete, name='book_bulk_delete'),
]

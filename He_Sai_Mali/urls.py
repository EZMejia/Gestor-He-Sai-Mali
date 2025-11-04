from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('pedido/', views.pedido, name='pedido'),
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
]
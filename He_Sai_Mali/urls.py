from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('pedido/', views.pedido, name='pedido'),
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('pedidos/', views.vista_mesero, name='pedidos'),
    path('registrarpedido/', views.vista_registrarpedido, name='registrarpedido'),
    path('cocina/', views.vista_cocinero, name='cocina'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('origen/', views.origen, name='origen'),
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('pedidos/', views.vista_mesero, name='pedidos'),
    path('pedidos/registrar/', views.vista_registrarpedido, name='registrarpedido'),
    
    #  --- Registrar un pedido EXISTENTE (Con ID) ---
    path('pedidos/registrar/<int:pedido_id>/', views.vista_registrarpedido, name='registrarpedido_agregar'),

    # --- Opciones para pedidos Pedidos ---
    path('pedidos/cambiar_estado/<int:pedido_platillo_id>/', views.cambiar_estado_platillo, name='cambiar_estado_platillo'),
    path('pedidos/facturar/<int:pedido_id>/', views.facturar_pedido, name='facturar_pedido'),
    path('pedidos/eliminar/<int:pedido_id>/', views.eliminar_pedido, name='eliminar_pedido'),
    # ------------------------------------------
    
    path('cocina/', views.vista_cocinero, name='cocina'),
    path('cocina/platillo_listo/<int:pedido_platillo_id>/', views.platillo_listo, name='platillo_listo'),

    # --- Vistas de Administrador (NUEVAS) ---
    path('ingredientes/', views.admin_ingredientes, name='admin_ingredientes'),
    path('ingredientes/agregar/', views.agregar_ingrediente, name='agregar_ingrediente'),
    path('ingredientes/comprar/', views.comprar_ingrediente, name='comprar_ingrediente'),
    path('platillos/', views.admin_platillos, name='admin_platillos'),
    path('platillos/toggle/<int:platillo_id>/', views.toggle_disponibilidad_platillo, name='toggle_disponibilidad_platillo'),
    path('proveedores/', views.admin_proveedores, name='admin_proveedores'),
    # ----------------------------------------

    path('logout/', views.logout_view, name='logout'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('pedidos/', views.vista_mesero, name='pedidos'),
    path('pedidos/registrar/', views.vista_registrarpedido, name='registrarpedido'),
    
    #  --- Registrar un pedido EXISTENTE (Con ID) ---
    path('pedidos/registrar/<int:pedido_id>/', views.vista_registrarpedido, name='registrarpedido_agregar'),

    # --- Opciones para pedidos Pedidos ---
    path('pedidos/cambiar_estado/<int:pedido_platillo_id>/', views.cambiar_estado_platillo, name='cambiar_estado_platillo'),
    
    path('pedidos/facturar/<int:pedido_id>/', views.facturar_pedido, name='facturar_pedido'),
    path('pedidos/factura/<int:pedido_id>/', views.mostrar_factura, name='mostrar_factura'), 
    path('pedidos/pagar/<int:pedido_id>/', views.pagar_factura, name='pagar_factura'),
    path('factura/descargar/<int:pedido_id>/', views.descargar_pdf_factura, name='descargar_pdf_factura'),

    path('pedidos/eliminar/<int:pedido_id>/', views.eliminar_pedido, name='eliminar_pedido'),
    # ------------------------------------------
    
    path('cocina/', views.vista_cocinero, name='cocina'),
    path('cocina/platillo_listo/<int:pedido_platillo_id>/', views.platillo_listo, name='platillo_listo'),

    # --- Vistas de Administrador (NUEVAS) ---
    path('ingredientes/', views.admin_ingredientes, name='admin_ingredientes'),
    path('ingredientes/editar/<int:ingrediente_id>/', views.editar_ingrediente, name='editar_ingrediente'),
    path('ingredientes/agregar/', views.agregar_ingrediente, name='agregar_ingrediente'),
    path('ingredientes/comprar/', views.comprar_ingrediente, name='comprar_ingrediente'),
    path('ingredientes/eliminar/<int:ingrediente_id>/', views.eliminar_ingrediente, name='eliminar_ingrediente'),
    path('platillos/', views.admin_platillos, name='admin_platillos'),
    path('platillos/editar/<int:platillo_id>/', views.editar_platillo, name='editar_platillo'),
    path('platillos/toggle/<int:platillo_id>/', views.toggle_disponibilidad_platillo, name='toggle_disponibilidad_platillo'),
    path('platillos/eliminar/<int:platillo_id>/', views.eliminar_platillo, name='eliminar_platillo'),
    path('proveedores/', views.admin_proveedores, name='admin_proveedores'),
    path('proveedores/editar/<int:proveedor_id>/', views.editar_proveedor, name='editar_proveedor'),
    path('proveedores/eliminar/<int:proveedor_id>/', views.eliminar_proveedor, name='eliminar_proveedor'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    # ----------------------------------------

    path('mesas/', views.admin_mesas, name='admin_mesas'),
    path('mesas/editar/<int:mesa_id>/', views.editar_mesa, name='editar_mesa'),
    path('mesas/eliminar/<int:mesa_id>/', views.eliminar_mesa, name='eliminar_mesa'),
    path('mesas/qr/<int:mesa_id>', views.vista_qr_mesas, name='qr_mesas'),
    
    # Vista del temporizador individual (el destino del código QR).
    path('temporizador/<int:mesa_id>/', views.temporizador_mesa, name='temporizador_mesa'),

    path('empleados/', views.admin_empleados, name='admin_empleados'),
    path('empleados/editar/<int:empleado_id>/', views.editar_empleado, name='editar_empleado'),
    path('empleados/eliminar/<int:empleado_id>/', views.eliminar_empleado, name='eliminar_empleado'),

    path('logout/', views.logout_view, name='logout'),
]
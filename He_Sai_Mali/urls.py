from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import api

router = DefaultRouter()
router.register(r'empleados-admin', api.EmpleadoAdminViewSet, basename='api_admin_empleados')
router.register(r'proveedores-admin', api.ProveedorViewSet, basename='api_admin_proveedores')
router.register(r'mesas-admin', api.MesaViewSet, basename='api_admin_mesas')
router.register(r'articulos-inventario', api.ArticuloInventarioViewSet, basename='api_articulos_inventario')
router.register(r'platillos-admin', api.ProductoMenuViewSet, basename='api_admin_platillos')

urlpatterns = [
    path('', views.main, name='main'),
    path('registro/', views.main_registro_html, name='registro'),
    path('api/empleados/registro/', api.RegistroEmpleadoAPIView.as_view(), name='api_registro_empleado'),
    path('api/', include(router.urls)),
    
    # --- Vistas de inicio ---
    path('login/', views.login_view_html, name='login'),
    path('api/login/', api.LoginAPIView.as_view(), name='api_login'),
    # ------------------------------------------

    # --- Vistas de generacion de pedidos --- 
    path('pedidos/', views.vista_mesero_html, name='pedidos'),
    path('pedidos/registrar/', views.vista_registrarpedido_html, name='registrarpedido'),
    # ------------------------------------------
    
    # --- Registrar un pedido EXISTENTE (Con ID) (Agregar productos a un pedido) ---
    path('pedidos/registrar/<int:pedido_id>/', views.vista_registrarpedido_html, name='registrarpedido_agregar'),
    # ------------------------------------------

    # Ruta para registrar un nuevo pedido
    path('api/pedidos/registrar/', api.RegistrarPedidoAPIView.as_view(), name='api_registrar_pedido'),
    
    # Ruta para obtener/actualizar un pedido existente
    path('api/pedidos/registrar/<int:pedido_id>/', api.RegistrarPedidoAPIView.as_view(), name='api_editar_pedido'),

    # --- Opciones para pedidos Pedidos ---
    path('api/pedidos/facturar/<int:pedido_id>/', api.FacturarPedidoAPIView.as_view(), name='api_facturar_pedido'),
    path('api/pedidos/pagar/<int:pedido_id>/', api.PagarFacturaAPIView.as_view(), name='api_pagar_factura'),

    path('pedidos/facturar/<int:pedido_id>/', views.facturar_pedido_html, name='facturar_pedido'),
    path('factura/descargar/<int:pedido_id>/', views.descargar_pdf_factura, name='descargar_pdf_factura'),

    path('api/pedidos/mesero-cola/', api.VistaMeseroAPIView.as_view(), name='api_vista_mesero'),
    path('api/pedidos/cambiar-estado/<int:pedido_platillo_id>/', api.CambiarEstadoPlatilloAPIView.as_view(), name='api_cambiar_estado_platillo'),
    path('api/pedidos/eliminar/<int:pedido_id>/', api.EliminarPedidoAPIView.as_view(), name='api_eliminar_pedido'),
    path('api/pedidos/registrar-merma/<int:pedido_platillo_id>/', api.RegistrarMermaPlatilloAPIView.as_view(), name='api_registrar_merma'),
    # ------------------------------------------
    
    # --- Vista para pedidos en la cocina ---
    path('cocina/', views.vista_cocinero_html, name='cocina'),
    path('api/cocina/', api.CocinaColaAPIView.as_view(), name='api_cocina_cola'),
    path('api/cocina/platillo_listo/<int:pedido_platillo_id>/', api.PlatilloListoAPIView.as_view(), name='api_platillo_listo'),
    # ------------------------------------------

    # --- Vistas de Administrador ---
    # --- Ingredientes ---
    path('ingredientes/', views.admin_ingredientes_html, name='admin_ingredientes'),
    # ----------------------------------------
    # --- Platillos ---
    path('platillos/', views.admin_platillos_html, name='admin_platillos'),
    # ----------------------------------------
    # --- Proveedores ---
    path('proveedores/', views.admin_proveedores_html, name='admin_proveedores'),
    # ----------------------------------------
    # --- Dashboard ---
    path('dashboard/', views.admin_dashboard_html, name='admin_dashboard'),
    path('dashboard/pdf/', views.generate_dashboard_pdf, name='generate_dashboard_pdf'),
    # --- API Dashboard ---
    path('api/dashboard/metrics/', api.AdminDashboardAPIView.as_view(), name='api_admin_dashboard_metrics'),
    # ----------------------------------------
    # --- Administracion de Empleados ---
    path('empleados/', views.admin_empleados_html, name='admin_empleados'),
    # ----------------------------------------

    # --- Vistas de administracion de mesas ---
    path('mesas/', views.admin_mesas_html, name='admin_mesas'),
    path('mesas/qr/<int:mesa_id>', views.vista_qr_mesas, name='qr_mesas'),
    # --- Vista del temporizador individual para cada mesa (el destino del código QR) ---
    path('temporizador/<int:mesa_id>/', views.temporizador_mesa, name='temporizador_mesa'),
    # ----------------------------------------

    # --- Historial de facturas ---
    path('historial-facturas/', views.historial_facturas_html, name='historial_facturas'),
    # --- API Historial de facturas ---
    path('api/historial-facturas/', api.HistorialFacturasAPIView.as_view(), name='api_historial_facturas'),
    path('api/historial-facturas/anular/<int:pedido_id>/', api.AnularFacturaAPIView.as_view(), name='api_anular_factura'),
    # ---------------------------------------- 

    # --- Logout ---
    path('logout/', views.logout_view, name='logout'),
    # ----------------------------------------   
]

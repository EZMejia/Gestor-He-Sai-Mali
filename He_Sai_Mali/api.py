from django.contrib.auth import authenticate, login
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction, connection
from django.contrib import messages
from django.db.models import Q, Sum, F, Max
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404
from itertools import groupby
from operator import attrgetter

from .serializers import *
from .models import *

# Importaciones adicionales para la funcionalidad de restablecimiento de contraseña
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import re

# Función auxiliar para obtener la sucursal activa del usuario
def obtener_sucursal_contexto(request):
    usuario = request.user
    if usuario.sucursal_id:
        return usuario.sucursal_id
    if usuario.rol == 'Administrador' and not usuario.sucursal_id:
        sucursal_sesion = request.session.get('sucursal_activa_id')
        if sucursal_sesion and str(sucursal_sesion) != 'todas':
            return int(sucursal_sesion)
    return None

# Función auxiliar para registrar acciones en la bitácora centralizada
def registrar_auditoria(request, modulo, accion, detalles, sucursal_afectada_id=None):
    try:
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
        if ip_address:
            ip_address = ip_address.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        if request and request.user.is_authenticated:
            empleado_id = request.user.idEmpleado
            usuario_nombre = f"{request.user.nombre} {request.user.apellido}"
            rol = request.user.rol
            sucursal_id = sucursal_afectada_id if sucursal_afectada_id else obtener_sucursal_contexto(request)
        else:
            empleado_id = None
            usuario_nombre = 'Sistema / No autenticado'
            rol = 'N/A'
            sucursal_id = None

        AuditoriaGeneral.objects.create(
            empleado_id=empleado_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            sucursal_id=sucursal_id,
            modulo=modulo,
            accion=accion,
            detalles=detalles,
            ip_address=ip_address
        )
    except Exception as e:
        print(f"Error al registrar auditoría: {str(e)}")

class EmpleadoAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Empleado.objects.all().order_by('apellido', 'nombre')
        sucursal_filtro = obtener_sucursal_contexto(self.request)
        if sucursal_filtro:
            queryset = queryset.filter(sucursal_id=sucursal_filtro)
        return queryset

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return EditarEmpleadoSerializer 
        return EmpleadoListSerializer

    def perform_update(self, serializer):
        empleado = serializer.save()
        registrar_auditoria(self.request, 'Empleados', 'Actualización', f"Se actualizaron los datos del empleado '{empleado.usuario}'.", sucursal_afectada_id=empleado.sucursal_id)

    def destroy(self, request, *bind, **kwargs):
        empleado = self.get_object()

        if empleado.idEmpleado == request.user.idEmpleado:
            return Response(
                {"error": "No puedes eliminar o desactivar tu propia cuenta de administrador."},
                status=status.HTTP_400_BAD_REQUEST
            )

        nombre_completo = f"{empleado.nombre} {empleado.apellido}"
        sucursal_id = empleado.sucursal_id

        try:
            empleado.delete()
            registrar_auditoria(request, 'Empleados', 'Eliminación', f"Se eliminó permanentemente al empleado '{nombre_completo}'.", sucursal_afectada_id=sucursal_id)
            return Response(
                {"message": f'El empleado "{nombre_completo}" ha sido ELIMINADO permanentemente.'},
                status=status.HTTP_200_OK
            )
        except ProtectedError:
            empleado.is_active = False
            empleado.save()
            registrar_auditoria(request, 'Empleados', 'Desactivación', f"Se desactivó al empleado '{nombre_completo}' por integridad referencial.", sucursal_afectada_id=sucursal_id)
            return Response(
                {"warning": f'El empleado "{nombre_completo}" no pudo ser eliminado por registros asociados. Ha sido DESACTIVADO.'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": f"Error al procesar la acción: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RegistroEmpleadoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sucursal_id = obtener_sucursal_contexto(request)
        
        if not sucursal_id:
            return Response(
                {"error": ["Debes seleccionar una sucursal específica en el menú superior para registrar un empleado."]}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        rol_solicitado = request.data.get('rol')
        if request.user.sucursal_id and rol_solicitado == 'Administrador':
            return Response(
                {"error": ["Operación denegada. Solo el Administrador Global puede crear nuevos administradores."]}, 
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RegistroEmpleadoSerializer(data=request.data)
        if serializer.is_valid():
            empleado = serializer.save(sucursal_id=sucursal_id)
            registrar_auditoria(request, 'Empleados', 'Creación', f"Se registró el nuevo empleado '{empleado.usuario}' con rol {empleado.rol}.", sucursal_afectada_id=sucursal_id)
            messages.success(request, f"Empleado registrado exitosamente. Su usuario asignado es: {empleado.usuario}")
            return Response({"status": "success"}, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        usuario = serializer.validated_data['usuario'].strip()
        contrasena = serializer.validated_data['contrasena']
        
        user = authenticate(request, username=usuario, password=contrasena)

        recordar = serializer.validated_data.get('recordar', False)

        if user is not None:
            if not user.is_active:
                return Response({'error': 'Este usuario se encuentra inactivo.'}, status=status.HTTP_400_BAD_REQUEST)
                
            login(request, user)

            if recordar:
                request.session.set_expiry(604800)  # Mantiene la sesión iniciada por 1 semanas (7 días)
            else:
                request.session.set_expiry(0)

            registrar_auditoria(request, 'Autenticación', 'Inicio de Sesión', f"El usuario '{user.usuario}' inició sesión exitosamente.", sucursal_afectada_id=user.sucursal_id)
            
            rol = (user.rol or '').strip().lower()
            if rol == "administrador":
                redirect_url = reverse('admin_dashboard')
            elif rol == "mesero":
                redirect_url = reverse('pedidos')
            elif rol == "cocinero":
                redirect_url = reverse('cocina')
            else:
                redirect_url = reverse('pedidos')
                
            return Response({'success': True, 'redirect_url': redirect_url}, status=status.HTTP_200_OK)
            
        return Response({'error': 'Usuario o contraseña incorrectos.'}, status=status.HTTP_400_BAD_REQUEST)
    
class ProveedorViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProveedorSerializer
    queryset = Proveedor.objects.all().order_by('idProveedor')

    def perform_create(self, serializer):
        prov = serializer.save()
        registrar_auditoria(self.request, 'Proveedores', 'Creación', f"Se registró el proveedor '{prov.nombre}'.")

    def perform_update(self, serializer):
        prov = serializer.save()
        registrar_auditoria(self.request, 'Proveedores', 'Actualización', f"Se actualizaron los datos del proveedor '{prov.nombre}'.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        nombre = instance.nombre
        try:
            instance.delete()
            registrar_auditoria(request, 'Proveedores', 'Eliminación', f"Se eliminó el proveedor '{nombre}'.")
            return Response(
                {"message": f'El proveedor "{nombre}" ha sido eliminado correctamente.'},
                status=status.HTTP_200_OK
            )
        except ProtectedError:
            return Response(
                {"error": f'Error al intentar eliminar: Asegúrate de que no haya ingredientes asociados a este proveedor.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class MesaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MesaSerializer
    lookup_field = 'idMesa'

    def get_queryset(self):
        queryset = Mesa.objects.all().order_by('idMesa')
        sucursal_filtro = obtener_sucursal_contexto(self.request)
        if sucursal_filtro:
            queryset = queryset.filter(sucursal_id=sucursal_filtro)
        return queryset

    def perform_create(self, serializer):
        # 1. Obtenemos la sucursal actual
        sucursal_id = obtener_sucursal_contexto(self.request)
        
        # 2. Validación de seguridad
        if not sucursal_id:
            raise serializers.ValidationError({"error": "Debes seleccionar una sucursal en el menú superior antes de registrar una mesa."})

        # 3. Guardamos pasando la sucursal_id explícitamente
        mesa = serializer.save(sucursal_id=sucursal_id)
        
        registrar_auditoria(self.request, 'Mesas', 'Creación', f"Se registró la Mesa N°{mesa.idMesa} con capacidad para {mesa.capacidad} personas.", sucursal_afectada_id=sucursal_id)

    def perform_update(self, serializer):
        # 1. Guardamos los cambios
        mesa = serializer.save()
        
        # 2. Registramos la actualización
        registrar_auditoria(
            self.request, 
            'Mesas', 
            'Actualización', 
            f"Se actualizaron los datos de la Mesa N°{mesa.idMesa}.", 
            sucursal_afectada_id=mesa.sucursal_id
        )

    def perform_destroy(self, instance):
        # 1. Guardamos los datos antes de borrar la instancia
        id_mesa = instance.idMesa
        suc_id = instance.sucursal_id
        
        # 2. Registramos la eliminación (antes de que desaparezca de la BD)
        registrar_auditoria(
            self.request, 
            'Mesas', 
            'Eliminación', 
            f"Se eliminó la Mesa N°{id_mesa} del sistema.", 
            sucursal_afectada_id=suc_id
        )
        
        # 3. Ejecutamos el borrado
        instance.delete()
class ArticuloInventarioViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticuloInventarioSerializer

    def get_queryset(self):
        queryset = ArticuloInventario.objects.all().order_by('nombre')
        sucursal_filtro = obtener_sucursal_contexto(self.request)
        if sucursal_filtro:
            queryset = queryset.filter(sucursal_id=sucursal_filtro)
        return queryset

    def perform_create(self, serializer):
        art = serializer.save()
        registrar_auditoria(self.request, 'Inventario', 'Creación', f"Artículo '{art.nombre}' registrado con stock inicial de {art.stock} {art.unidad_de_medida}.", sucursal_afectada_id=art.sucursal_id)

    def perform_update(self, serializer):
        art = serializer.save()
        registrar_auditoria(self.request, 'Inventario', 'Actualización', f"Datos del artículo '{art.nombre}' actualizados.", sucursal_afectada_id=art.sucursal_id)

    def perform_destroy(self, instance):
        nombre = instance.nombre
        suc = instance.sucursal_id
        instance.delete()
        registrar_auditoria(self.request, 'Inventario', 'Eliminación', f"Artículo '{nombre}' eliminado del inventario.", sucursal_afectada_id=suc)

    @action(detail=True, methods=['post'], url_path='comprar')
    def comprar(self, request, pk=None):
        articulo = self.get_object()
        serializer = CompraIngredienteSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        id_proveedor = serializer.validated_data['id_proveedor_fk']
        precio_compra = serializer.validated_data['precio_compra']
        cantidad_comprada = serializer.validated_data['cantidad_comprada']
        fecha_compra = serializer.validated_data['fecha_compra']
        
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    sql_insert_compra = """
                        INSERT INTO "ArticuloInventario_Proveedor" 
                        ("idArticuloInventario_id", "idProveedor_id", "precioCompra", "cantidadCompra", "fechaCompra")
                        VALUES (%s, %s, %s, %s, %s);
                    """
                    cursor.execute(sql_insert_compra, [
                        articulo.pk, 
                        id_proveedor, 
                        precio_compra, 
                        cantidad_comprada,
                        fecha_compra
                    ])

                ArticuloInventario.objects.filter(pk=articulo.pk).update(
                    stock=F('stock') + cantidad_comprada
                )
                
            registrar_auditoria(request, 'Inventario', 'Compra', f"Se registraron {cantidad_comprada} {articulo.unidad_de_medida} al stock de '{articulo.nombre}'.", sucursal_afectada_id=articulo.sucursal_id)
            return Response({
                'success': True, 
                'message': f'Compra registrada exitosamente. Se agregaron {cantidad_comprada} {articulo.unidad_de_medida} al stock.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'Error al procesar la transacción en la base de datos: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='registrar-merma')
    def registrar_merma(self, request, pk=None):
        serializer = MermaIngredienteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        cantidad_merma = serializer.validated_data['cantidad_merma']
        
        try:
            with transaction.atomic():
                articulo = ArticuloInventario.objects.select_for_update().get(pk=pk)
                
                stock_actual = Decimal(str(articulo.stock))
                descuento_merma = Decimal(str(cantidad_merma))
                
                if descuento_merma > stock_actual:
                    return Response({
                        'error': f'No puedes descontar {cantidad_merma}. El stock actual de "{articulo.nombre}" es de {articulo.stock}.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                articulo.stock = stock_actual - descuento_merma
                articulo.save()
                
            registrar_auditoria(request, 'Inventario', 'Merma', f"Se registró pérdida de {cantidad_merma} {articulo.unidad_de_medida} en el stock de '{articulo.nombre}'.", sucursal_afectada_id=articulo.sucursal_id)
            return Response({
                'success': True,
                'message': f'Pérdida registrada: Se descontaron {cantidad_merma} {articulo.unidad_de_medida} de "{articulo.nombre}".'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'Ocurrió un error inesperado al procesar el descuento de merma: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
class ProductoMenuViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ProductoMenu.objects.all().order_by('idProductoMenu')
    serializer_class = ProductoMenuSerializer

    def perform_create(self, serializer):
        prod = serializer.save()
        registrar_auditoria(self.request, 'Menú', 'Creación', f"Se registró el platillo '{prod.nombre}'.")

    def perform_update(self, serializer):
        prod = serializer.save()
        registrar_auditoria(self.request, 'Menú', 'Actualización', f"Se actualizaron los datos del platillo '{prod.nombre}'.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        nombre_platillo = instance.nombre
        try:
            self.perform_destroy(instance)
            registrar_auditoria(request, 'Menú', 'Eliminación', f"Se eliminó el platillo '{nombre_platillo}'.")
            return Response(
                {"detail": f'El platillo "{nombre_platillo}" ha sido eliminado exitosamente.'},
                status=status.HTTP_200_OK
            )
        except ProtectedError:
            return Response(
                {"detail": f'No se puede eliminar el platillo "{nombre_platillo}" porque tiene pedidos asociados. Debe eliminar los pedidos relacionados primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"detail": f'Ocurrió un error inesperado al intentar eliminar el platillo: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='toggle-disponibilidad')
    def toggle_disponibilidad(self, request, pk=None):
        platillo = self.get_object()
        try:
            platillo.disponible = not platillo.disponible
            platillo.save()
            
            estado = "Disponible" if platillo.disponible else "No Disponible"
            registrar_auditoria(request, 'Menú', 'Cambio Disponibilidad', f"El platillo '{platillo.nombre}' ahora está {estado}.")
            return Response({
                "detail": f'Estado de "{platillo.nombre}" cambiado a: {estado}.',
                "disponible": platillo.disponible
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": f'Error al cambiar disponibilidad: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], url_path='categorias')
    def obtener_categorias(self, request):
        categorias = ProductoMenu.objects.values_list('categoria', flat=True).distinct()
        return Response(list(categorias), status=status.HTTP_200_OK)
    
class AdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        ingredientes_insuficientes = VistaAlertasStock.objects.filter(porciones_posibles__lt=5).values(
            'ingrediente', 'stock', 'unidad_de_medida'
        )
        
        ingredientes_formateados = [
            {
                'nombre': item['ingrediente'],
                'cantidad_actual': float(item['stock']),
                'unidad_medida': item['unidad_de_medida']
            } for item in ingredientes_insuficientes
        ]

        hoy_str = date.today().isoformat()
        is_search = bool(request.query_params) 

        if not is_search:
            start_date_str = hoy_str
            end_date_str = hoy_str
            search_query = ''
        else:
            start_date_str = request.query_params.get('start_date', '')
            end_date_str = request.query_params.get('end_date', '')
            search_query = request.query_params.get('search', '').strip()

            if search_query and start_date_str == hoy_str and end_date_str == hoy_str:
                start_date_str = ''
                end_date_str = ''

        today_dt = timezone.localtime(timezone.now())

        if start_date_str:
            try:
                start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
            except (ValueError, TypeError):
                start_date = timezone.make_aware(datetime.combine(date.today(), datetime.min.time()))
        else:
            start_date = timezone.make_aware(datetime(2000, 1, 1))

        if end_date_str:
            try:
                end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
            except (ValueError, TypeError):
                end_date = timezone.make_aware(datetime.combine(date.today(), datetime.max.time()))
        else:
            end_date = timezone.make_aware(datetime(2100, 1, 1))

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        if end_date > today_dt:
            end_date = today_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        if start_date > end_date:
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        total_sales = 0.00
        total_orders = 0
        top_products_labels, top_products_data = [], []
        top_tables_labels, top_tables_data = [], []
        total_mesas = Mesa.objects.count()
        platillos_en_menu = ProductoMenu.objects.filter(disponible=True).count()
        search_results = []
        search_results_count = 0

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        CALL sp_resumen_dashboard(
                            %s::TIMESTAMPTZ, 
                            %s::TIMESTAMPTZ, 
                            %s::VARCHAR, 
                            %s::INTEGER[]
                        )
                    """, [start_date, end_date, search_query, None])
                    
                    cursor.execute("SELECT * FROM temp_metricas_dashboard")
                    metricas = cursor.fetchone()
                    
                    if metricas:
                        total_sales = float(metricas[0])    
                        total_orders = metricas[1]          
                        if metricas[3]: total_mesas = metricas[3]
                        if metricas[4]: platillos_en_menu = metricas[4]
                    
                    cursor.execute("SELECT nombre_producto, cantidad_total FROM temp_top_productos")
                    productos = cursor.fetchall()
                    top_products_labels = [p[0] for p in productos]
                    top_products_data = [float(p[1]) for p in productos]
                    
                    cursor.execute("SELECT numero_mesa, total_pedidos FROM temp_top_mesas")
                    mesas = cursor.fetchall()
                    top_tables_labels = [f"Mesa {m[0]}" for m in mesas]
                    top_tables_data = [m[1] for m in mesas]
                    
                    if search_query:
                        cursor.execute("SELECT * FROM temp_busqueda_clientes")
                        columnas = [col[0] for col in cursor.description]
                        resultados = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
                        
                        if resultados:
                            search_results_count = resultados[0].get('total_encontrados', 0)
                            
                            for r in resultados:
                                search_results.append({
                                    'idPedido': r['id_pedido'],
                                    'idCliente': {'nombre': r.get('nombre_cliente', '')},
                                    'fecha': r.get('fecha_pedido'),
                                    'idMesa': {'idMesa': r['mesa_numero']} if r.get('mesa_numero') else None,
                                    'montoTotal': float(r.get('monto_total', 0)),
                                    'metodoPago': r.get('metodo_pago', 'N/A'),
                                    'estadoDePago': r.get('estado_pago', True)
                                })
                                
        except Exception as e:
            return Response(
                {"error": f"Error en procedimiento almacenado: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        search_compras = request.query_params.get('search_compras', '').strip()
        compras_query = ArticuloInventario_Proveedor.objects.select_related(
            'idArticuloInventario', 'idProveedor'
        )

        historial_compras = []
        for compra in compras_query:
            historial_compras.append({
                'fecha': compra.fechaCompra,
                'ingrediente': compra.idArticuloInventario.nombre,
                'proveedor': compra.idProveedor.nombre,
                'cantidad': float(compra.cantidadCompra),
                'unidad': compra.idArticuloInventario.unidad_de_medida, 
                'total': float(compra.precioCompra),
            })

        data = {
            'metricas': {
                'total_sales': total_sales,
                'total_orders': total_orders,
                'total_mesas': total_mesas,
                'platillos_en_menu': platillos_en_menu,
            },
            'fechas_filtro': {
                'start_date_obj': start_date,
                'end_date_obj': end_date,
                'start_date_str': start_date_str,
                'end_date_str': end_date_str,
            },
            'graficos': {
                'top_products': {
                    'labels': top_products_labels,
                    'data': top_products_data
                },
                'top_tables': {
                    'labels': top_tables_labels,
                    'data': top_tables_data
                }
            },
            'busqueda_clientes': {
                'search_query': search_query,
                'search_results_count': search_results_count,
                'search_results': search_results,
            },
            'ingredientes_insuficientes': ingredientes_formateados,
            'compras': {
                'search_compras': search_compras,
                'historial_compras': historial_compras,
            }
        }

        return Response(data, status=status.HTTP_200_OK)
    
class HistorialFacturasAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hoy_str = date.today().isoformat()
        is_search = bool(request.query_params)
        
        q = request.query_params.get('q', '').strip()
        estado = request.query_params.get('estado', 'TODOS')
        
        if not is_search:
            fecha_inicio = hoy_str
            fecha_fin = hoy_str
        else:
            fecha_inicio = request.query_params.get('fecha_inicio', '')
            fecha_fin = request.query_params.get('fecha_fin', '')
            
            if q and fecha_inicio == hoy_str and fecha_fin == hoy_str:
                fecha_inicio = ''
                fecha_fin = ''

        facturas = Pedido.objects.filter(
            Q(estadoDePago=True, estado_factura='VIGENTE') | 
            Q(estado_factura='ANULADA')
        ).order_by('-fecha')

        sucursal_filtro = obtener_sucursal_contexto(request)
        if sucursal_filtro:
            facturas = facturas.filter(sucursal_id=sucursal_filtro)
            
        if q:
            if q.isdigit():
                facturas = facturas.filter(idPedido=q)
            else:
                facturas = facturas.filter(idCliente__nombre__icontains=q)

        if fecha_inicio:
            facturas = facturas.filter(fecha__date__gte=fecha_inicio)
        if fecha_fin:
            facturas = facturas.filter(fecha__date__lte=fecha_fin)

        if estado != 'TODOS':
            facturas = facturas.filter(estado_factura=estado)

        suma_base = facturas.filter(estado_factura='VIGENTE').aggregate(Sum('montoTotal'))['montoTotal__sum'] or 0.00
        ventas_totales = float(suma_base) * 1.15
        total_facturas = facturas.count()
        total_clientes = facturas.values('idCliente').distinct().count()

        serializer = FacturaHistorialSerializer(facturas, many=True)

        return Response({
            'metricas': {
                'ventas_totales': round(ventas_totales, 2),
                'total_facturas': total_facturas,
                'total_clientes': total_clientes
            },
            'filtros': {
                'q': q,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'estado': estado
            },
            'facturas': serializer.data
        }, status=status.HTTP_200_OK)

class AnularFacturaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pedido_id):
        serializer = AnularFacturaSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        motivo = serializer.validated_data['motivo_anulacion']
        
        try:
            pedido = Pedido.objects.get(pk=pedido_id)
        except Pedido.DoesNotExist:
            return Response({'error': 'La factura solicitada no existe.'}, status=status.HTTP_404_NOT_FOUND)
            
        if pedido.estado_factura != 'VIGENTE':
            return Response(
                {'warning': f'La factura N°{pedido.idPedido} ya se encuentra anulada.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            with transaction.atomic():
                pedido.estado_factura = 'ANULADA'
                pedido.estadoDePago = False
                pedido.save()
                
                # --- MEJORA PARA LA AUDITORÍA ---
                if motivo == 'error_cobro':
                    mensaje = f'Factura N°{pedido.idPedido} anulada por error de cobro. Inventario físico intacto.'
                    tipo_alerta = 'success'
                    motivo_legible = 'Error de cobro / Refacturación'
                    accion_inventario = 'Inventario físico intacto'
                    
                elif motivo == 'rechazo':
                    mensaje = f'Factura N°{pedido.idPedido} anulada. Los insumos se registran como merma.'
                    tipo_alerta = 'warning'
                    motivo_legible = 'Comida devuelta / Desperdicio'
                    accion_inventario = 'Insumos registrados como merma'
                    
                elif motivo == 'duplicado':
                    platillos_vendidos = Pedido_ProductoMenu.objects.filter(idPedido=pedido)
                    
                    for item_pedido in platillos_vendidos:
                        cantidad_pedida = item_pedido.cantidad
                        producto = item_pedido.idProductoMenu
                        
                        receta_ingredientes = ProductoMenu_ArticuloInventario.objects.filter(idProductoMenu=producto)
                        
                        for ingrediente in receta_ingredientes:
                            cantidad_a_devolver = ingrediente.cantidad_usada * cantidad_pedida
                            articulo = ingrediente.idArticuloInventario
                            
                            articulo.stock = F('stock') + cantidad_a_devolver
                            articulo.save()
                            
                    mensaje = f'Factura N°{pedido.idPedido} anulada. Insumos devueltos al stock (Orden duplicada).'
                    tipo_alerta = 'success'
                    motivo_legible = 'Pedido duplicado por error'
                    accion_inventario = 'Insumos devueltos al stock'
                    
            registrar_auditoria(
                request, 
                'Facturación', 
                'Anulación de Factura', 
                f"Factura N°{pedido.idPedido} anulada. Motivo: {motivo_legible}. Acción: {accion_inventario}.", 
                sucursal_afectada_id=pedido.sucursal_id
            )
            return Response({'mensaje': mensaje, 'tipo_alerta': tipo_alerta}, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Ocurrió un error interno al procesar la anulación: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CocinaColaAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        pedidos_pendientes = VistaPedidosCocina.objects.all().order_by('fecha', 'id')
        id_mas_antiguo = pedidos_pendientes.first().id_pedido if pedidos_pendientes.exists() else None

        ahora = timezone.now()
        pedidos_activos = {}
        alertas = []

        for pp in pedidos_pendientes:
            pedido_id = pp.id_pedido
            
            if pedido_id not in pedidos_activos:
                items_validos = Pedido_ProductoMenu.objects.filter(
                    idPedido=pedido_id
                ).exclude(
                    estado__in=['Anulado', 'Merma']
                )
                
                agregados = items_validos.aggregate(
                    tiempo_maximo=Max('idProductoMenu__tiempoPreparacion'),
                    total_quantity=Sum('cantidad')
                )
                
                tiempo_base_segundos = agregados.get('tiempo_maximo') or 0
                total_quantity = agregados.get('total_quantity') or 0
                
                tiempo_logistica_segundos = total_quantity * 45
                tiempo_servicio_segundos = 60
                tiempo_total_segundos = tiempo_base_segundos + tiempo_logistica_segundos + tiempo_servicio_segundos
                
                tiempo_limite = pp.fecha + timedelta(seconds=tiempo_total_segundos) 
                
                retrasado = ahora > tiempo_limite
                if retrasado:
                    alertas.append(f"¡El Pedido #{pedido_id} lleva mucho tiempo de retraso!")

                numero_mesa = f"Mesa: {pp.id_mesa}" if pp.id_mesa else "Sin Mesa"
                pedidos_activos[pedido_id] = {
                    'id': pedido_id,
                    'cliente': pp.nombre_cliente,
                    'mesa': numero_mesa,
                    'hora': pp.fecha,
                    'es_mas_antiguo': pedido_id == id_mas_antiguo,
                    'retrasado': retrasado,
                    'platillos': []
                }
            
            pedidos_activos[pedido_id]['platillos'].append({
                'id_pp': pp.id,
                'nombre': pp.nombre_platillo,
                'cantidad': pp.cantidad,
            })
        
        return Response({
            'pedidos_en_cola': list(pedidos_activos.values()),
            'alertas': alertas
        }, status=status.HTTP_200_OK)

class PlatilloListoAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pedido_platillo_id):
        try:
            with connection.cursor() as cursor:
                sql_select = """
                    SELECT p."idProductoMenu_id", p."idPedido_id" FROM "Pedido_ProductoMenu" p
                    WHERE "idPedido_ProductoMenu" = %s AND "estado" = 'Registrado';
                """
                cursor.execute(sql_select, [pedido_platillo_id])
                result = cursor.fetchone()
                
                if not result:
                    return Response({
                        "error": "El platillo no se encontró o su estado ya no es 'Registrado'."
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                platillo_id = result[0]
                pedido_id = result[1]
                
                sql_get_nombre = """
                    SELECT "nombre" FROM "ProductoMenu" WHERE "idProductoMenu" = %s;
                """
                cursor.execute(sql_get_nombre, [platillo_id])
                nombre_platillo = cursor.fetchone()[0]

                sql_update = """
                    UPDATE "Pedido_ProductoMenu"
                    SET "estado" = 'Listo'
                    WHERE "idPedido_ProductoMenu" = %s;
                """
                cursor.execute(sql_update, [pedido_platillo_id])
                
            registrar_auditoria(request, 'Cocina', 'Platillo Listo', f"Platillo '{nombre_platillo}' del Pedido N°{pedido_id} marcado como listo.")

            return Response({
                "message": f"El platillo '{nombre_platillo}' para el Pedido N°{pedido_id} ha sido marcado como LISTO."
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Error al marcar como listo: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VistaMeseroAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cola_pedidos = list(Pedido.objects.raw("""
            SELECT p."idPedido", p."fecha", p."metodoPago", c."nombre", p."idMesa_id", p."montoTotal"
            FROM "Pedido" p
            JOIN "Cliente" c ON c."idCliente" = p."idCliente_id"
            JOIN "Empleado_Pedido" ep ON ep."idPedido_id" = p."idPedido"
            WHERE p."idPedido" IN (
                SELECT pp."idPedido_id" FROM "Pedido_ProductoMenu" pp
                WHERE pp."estado" IN ('Registrado', 'Listo', 'Servido')
                GROUP BY pp."idPedido_id"
            ) AND ep."idEmpleado_id" = %s
            GROUP BY p."idPedido", p."fecha", p."metodoPago", c."nombre", p."idMesa_id", p."montoTotal"
            ORDER BY p."fecha" ASC;
        """, [request.user.idEmpleado]))

        pedidos_ids = [p.idPedido for p in cola_pedidos]

        ProductoMenu_query = Pedido_ProductoMenu.objects.filter(
            idPedido__in=pedidos_ids
        ).exclude(
            estado__in=['Merma', 'Anulado']
        ).select_related('idProductoMenu').order_by('idPedido_id')

        platillos_por_pedido = {}
        for pp in ProductoMenu_query:
            if pp.idPedido_id not in platillos_por_pedido:
                platillos_por_pedido[pp.idPedido_id] = []
            platillos_por_pedido[pp.idPedido_id].append(pp)

        serializer = PedidoColaSerializer(
            cola_pedidos, 
            many=True, 
            context={'platillos_por_pedido': platillos_por_pedido}
        )

        return Response({
            "nombre_mesero": f"{request.user.nombre} {request.user.apellido}",
            "rol": request.user.rol,
            "metodos_pago": ['Efectivo', 'Tarjeta', 'Transferencia'],
            "cola_pedidos": serializer.data
        }, status=status.HTTP_200_OK)


class CambiarEstadoPlatilloAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pedido_platillo_id):
        pedido_ProductoMenu = get_object_or_404(Pedido_ProductoMenu, pk=pedido_platillo_id)
        current_state = pedido_ProductoMenu.estado
        next_state = None

        if current_state == 'Registrado':
            next_state = 'Listo'
        elif current_state == 'Listo':
            next_state = 'Servido'

        if not next_state:
            return Response(
                {"detail": f"El platillo ya se encuentra en estado '{current_state}' y no puede avanzar más."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with connection.cursor() as cursor:
            sql_update_estado = """
                UPDATE "Pedido_ProductoMenu"
                SET "estado" = %s
                WHERE "idPedido_ProductoMenu" = %s;
            """
            cursor.execute(sql_update_estado, [next_state, pedido_platillo_id])
            
        registrar_auditoria(request, 'Pedidos', 'Cambio Estado', f"El platillo '{pedido_ProductoMenu.idProductoMenu.nombre}' en Pedido N°{pedido_ProductoMenu.idPedido.idPedido} avanzó a estado '{next_state}'.", sucursal_afectada_id=pedido_ProductoMenu.idPedido.sucursal_id)

        return Response({
            "message": f"Estado de {pedido_ProductoMenu.idProductoMenu.nombre} cambiado a '{next_state}'.",
            "idPedido_Platillo": pedido_platillo_id,
            "nuevo_estado": next_state
        }, status=status.HTTP_200_OK)


class EliminarPedidoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pedido_id):
        pedido = get_object_or_404(Pedido, pk=pedido_id)
        suc_id = pedido.sucursal_id

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    
                    sql_check = """
                        SELECT COUNT(*) FROM "Pedido_ProductoMenu"
                        WHERE "idPedido_id" = %s AND "estado" IN ('Listo', 'Servido');
                    """
                    cursor.execute(sql_check, [pedido_id])
                    items_bloqueantes = cursor.fetchone()[0]

                    if items_bloqueantes > 0:
                        return Response(
                            {"detail": f"No se puede eliminar el Pedido N°{pedido_id} porque aún tiene productos Listos o Servidos en la mesa."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    sql_registrados = """
                        SELECT "idProductoMenu_id", "cantidad" 
                        FROM "Pedido_ProductoMenu"
                        WHERE "idPedido_id" = %s AND "estado" = 'Registrado';
                    """
                    cursor.execute(sql_registrados, [pedido_id])
                    platillos_registrados = cursor.fetchall()

                    for id_producto, cantidad in platillos_registrados:
                        sql_receta = """
                            SELECT "idArticuloInventario_id", "cantidad_usada" 
                            FROM "ProductoMenu_ArticuloInventario" 
                            WHERE "idProductoMenu_id" = %s;
                        """
                        cursor.execute(sql_receta, [id_producto])
                        ingredientes = cursor.fetchall()

                        for id_ingrediente, cant_unitaria in ingredientes:
                            cant_devolver = Decimal(str(cant_unitaria)) * Decimal(str(cantidad))
                            sql_update_stock = """
                                UPDATE "ArticuloInventario" 
                                SET "stock" = "stock" + %s 
                                WHERE "idArticuloInventario" = %s;
                            """
                            cursor.execute(sql_update_stock, [cant_devolver, id_ingrediente])

                    if pedido.idMesa:
                        mesa = pedido.idMesa
                        mesa.ocupada = False
                        mesa.save()

                    pedido.delete()
                    
            registrar_auditoria(request, 'Pedidos', 'Eliminación', f"Pedido N°{pedido_id} eliminado exitosamente. Insumos activos retornados.", sucursal_afectada_id=suc_id)

            return Response(
                {"message": f"Pedido N°{pedido_id} eliminado exitosamente. Los insumos activos regresaron al inventario."}, 
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"detail": f"Error interno al eliminar: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class RegistrarMermaPlatilloAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pedido_platillo_id):
        pedido_platillo = get_object_or_404(Pedido_ProductoMenu, pk=pedido_platillo_id)
        estado_actual = pedido_platillo.estado
        nombre_platillo = pedido_platillo.idProductoMenu.nombre
        producto = pedido_platillo.idProductoMenu
        cantidad_pedida = pedido_platillo.cantidad
        suc_id = pedido_platillo.idPedido.sucursal_id

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    if estado_actual == 'Registrado' or (getattr(producto, 'tiempoPreparacion', 0) == 0 and estado_actual != 'Servido'):
                        nuevo_estado = 'Anulado'
                        
                        sql_receta = """
                            SELECT "idArticuloInventario_id", "cantidad_usada" 
                            FROM "ProductoMenu_ArticuloInventario" 
                            WHERE "idProductoMenu_id" = %s;
                        """
                        cursor.execute(sql_receta, [producto.idProductoMenu])
                        ingredientes = cursor.fetchall()

                        for id_ingrediente, cant_unitaria_usada in ingredientes:
                            cantidad_a_devolver = Decimal(str(cant_unitaria_usada)) * Decimal(str(cantidad_pedida))
                            sql_update_stock = """
                                UPDATE "ArticuloInventario" 
                                SET "stock" = "stock" + %s 
                                WHERE "idArticuloInventario" = %s;
                            """
                            cursor.execute(sql_update_stock, [cantidad_a_devolver, id_ingrediente])
                    else:
                        nuevo_estado = 'Merma'

                    sql_update = """
                        UPDATE "Pedido_ProductoMenu"
                        SET "estado" = %s
                        WHERE "idPedido_ProductoMenu" = %s;
                    """
                    cursor.execute(sql_update, [nuevo_estado, pedido_platillo_id])
                    
                pedido = pedido_platillo.idPedido
                items_activos = Pedido_ProductoMenu.objects.filter(
                    idPedido=pedido
                ).exclude(estado__in=['Anulado', 'Merma']).count()

                mesa_liberada = False
                if items_activos == 0 and pedido.idMesa:
                    mesa_a_liberar = pedido.idMesa
                    mesa_a_liberar.ocupada = False
                    mesa_a_liberar.save()
                    mesa_liberada = True

            if nuevo_estado == 'Anulado':
                message = f"'{nombre_platillo}' cancelado con éxito. Los productos se devolvieron al inventario."
                tipo_notificacion = "success"
            else:
                message = f"'{nombre_platillo}' enviado a Mermas (Pérdida de inventario)."
                tipo_notificacion = "warning"

            registrar_auditoria(request, 'Pedidos', f'Registro de {nuevo_estado}', f"Platillo '{nombre_platillo}' en Pedido N°{pedido.idPedido} modificado a {nuevo_estado}.", sucursal_afectada_id=suc_id)

            return Response({
                "message": message,
                "nuevo_estado": nuevo_estado,
                "tipo_notificacion": tipo_notificacion,
                "idPedido_Platillo": pedido_platillo_id,
                "mesa_liberada": mesa_liberada
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": f"Error al registrar la merma: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

def calcular_monto_total(pedido_id):
    pedido = Pedido.objects.filter(pk=pedido_id).first()
    if pedido and pedido.montoTotal:
        return float(pedido.montoTotal)
    return 0.0

class FacturarPedidoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pedido_id):
        if not request.user.is_authenticated or request.user.rol != 'Mesero':
            return Response({"error": "No tienes permisos de Mesero."}, status=status.HTTP_403_FORBIDDEN)

        pedido = get_object_or_404(Pedido, pk=pedido_id)
        
        monto_total = calcular_monto_total(pedido_id)
        platillos_pedido = Pedido_ProductoMenu.objects.filter(
            idPedido=pedido
        ).exclude(estado__in=['Merma', 'Anulado']).select_related('idProductoMenu')
        
        TASA_IMPUESTO = Decimal('0.15')
        monto_total_decimal = Decimal(str(monto_total))

        if monto_total_decimal:
            subtotal = monto_total_decimal
            impuesto = monto_total_decimal * TASA_IMPUESTO
        else:
            subtotal = Decimal('0.00')
            impuesto = Decimal('0.00')
        
        cliente = pedido.idCliente

        platillos_data = [{
            'producto': item.idProductoMenu.nombre,
            'cantidad': item.cantidad,
            'precio_unitario': item.idProductoMenu.precio,
            'total_platillo': round(item.cantidad * item.idProductoMenu.precio, 2)
        } for item in platillos_pedido]

        return Response({
            'factura': {
                'id_pedido': pedido.idPedido,
                'fecha': pedido.fecha,
                'metodo_pago': pedido.metodoPago,
                'estado_pago': 'Pagada' if pedido.estadoDePago == 1 else 'Pendiente'
            },
            'cliente': {
                'nombre_completo': cliente.nombre,
                'identificacion': cliente.identificacion,
                'tipo_cliente': cliente.tipoCliente
            },
            'platillos': platillos_data,
            'totales': {
                'subtotal': round(subtotal, 2),
                'impuesto': round(impuesto, 2),
                'monto_total': round(monto_total_decimal + impuesto, 2)
            }
        }, status=status.HTTP_200_OK)

    def post(self, request, pedido_id):
        if not request.user.is_authenticated or request.user.rol != 'Mesero':
            return Response({"error": "No tienes permisos de Mesero."}, status=status.HTTP_403_FORBIDDEN)

        pedido = get_object_or_404(Pedido, pk=pedido_id)
        
        metodo_pago = request.data.get('metodo_pago')
        
        if not metodo_pago:
            return Response({"error": "Debe proporcionar un método de pago."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            pedido.metodoPago = metodo_pago
            pedido.save()

        registrar_auditoria(request, 'Facturación', 'Método de Pago Asignado', f"Se asignó '{metodo_pago}' al Pedido N°{pedido.idPedido}.", sucursal_afectada_id=pedido.sucursal_id)

        return Response({
            "status": "success", 
            "message": f"Método de pago '{metodo_pago}' asignado exitosamente."
        }, status=status.HTTP_200_OK)


class PagarFacturaAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pedido_id):
        if not request.user.is_authenticated or request.user.rol != 'Mesero':
            return Response({"error": "No tienes permisos de Mesero."}, status=status.HTTP_403_FORBIDDEN)

        pedido = get_object_or_404(Pedido, pk=pedido_id)

        try:
            with transaction.atomic():
                pedido.estadoDePago = 1 
                pedido.estado_factura = 'VIGENTE' 
                pedido.save()
                
                with connection.cursor() as cursor:
                    sql_update_facturar = """
                        UPDATE "Pedido_ProductoMenu"
                        SET "estado" = 'Facturado'
                        WHERE "idPedido_id" = %s AND "estado" IN ('Registrado', 'Listo', 'Servido');
                    """
                    cursor.execute(sql_update_facturar, [pedido_id])
                        
                if pedido.idMesa:
                    mesa_a_liberar = pedido.idMesa
                    mesa_a_liberar.ocupada = False
                    mesa_a_liberar.save()

            registrar_auditoria(request, 'Facturación', 'Pago Completado', f"El Pedido N°{pedido.idPedido} ha sido marcado como pagado exitosamente.", sucursal_afectada_id=pedido.sucursal_id)

            return Response({
                "status": "success", 
                "message": f"Pago registrado exitosamente para el Pedido N°{pedido.idPedido}. Factura completada."
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "status": "error", 
                "message": f"Error en el procesamiento del pago: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class RegistrarPedidoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pedido_id=None):
        if request.user.rol != "Mesero":
            return Response({"error": "No tienes permisos para acceder a esta vista."}, status=status.HTTP_403_FORBIDDEN)

        inventario_actual = {
            art.idArticuloInventario: float(art.stock)
            for art in ArticuloInventario.objects.all()
        }

        recetas = {}
        relaciones = ProductoMenu_ArticuloInventario.objects.all()
        for rel in relaciones:
            if rel.idProductoMenu_id not in recetas:
                recetas[rel.idProductoMenu_id] = []
            recetas[rel.idProductoMenu_id].append({
                'idArticulo': rel.idArticuloInventario_id,
                'cantidad': float(rel.cantidad_usada)
            })

        all_menu = list(ProductoMenu.objects.raw("""
            SELECT * FROM "ProductoMenu" WHERE "disponible" = 'true' ORDER BY "categoria", "nombre"
        """))
        
        platillos_agrupados = {
            categoria: [
                {
                    "idProductoMenu": p.idProductoMenu,
                    "nombre": p.nombre,
                    "precio": float(p.precio),
                    "tiempoPreparacion": p.tiempoPreparacion
                } for p in platillos
            ]
            for categoria, platillos in groupby(all_menu, key=attrgetter('categoria'))
        }

        pedido_existente_data = None
        platillos_previos = []

        if pedido_id:
            sql_pedido = """
                SELECT p."idPedido", p."idCliente_id", p."idMesa_id", p."montoTotal", p."fecha", 
                        c."nombre" AS "cliente_nombre", c."telefono" AS "cliente_telefono"
                FROM "Pedido" p
                JOIN "Cliente" c ON c."idCliente" = p."idCliente_id"
                WHERE p."idPedido" = %s;
            """
            pedido_raw = list(Pedido.objects.raw(sql_pedido, [pedido_id]))
            
            if pedido_raw:
                p_data = pedido_raw[0]
                pedido_existente_data = {
                    "idPedido": p_data.idPedido,
                    "montoTotal": float(p_data.montoTotal),
                    "idMesa": p_data.idMesa_id,
                    "cliente": {
                        "nombre": p_data.cliente_nombre,
                        "telefono": p_data.cliente_telefono,
                        "idCliente": p_data.idCliente_id
                    }
                }

            with connection.cursor() as cursor:
                sql_detalles = """
                    SELECT pm.nombre, pp.cantidad, pm.precio, (pp.cantidad * pm.precio) as subtotal
                    FROM "Pedido_ProductoMenu" pp
                    JOIN "ProductoMenu" pm ON pp."idProductoMenu_id" = pm."idProductoMenu"
                    WHERE pp."idPedido_id" = %s;
                """
                cursor.execute(sql_detalles, [pedido_id])
                columns = [col[0] for col in cursor.description]
                platillos_previos = [dict(zip(columns, row)) for row in cursor.fetchall()]

        mesas_disponibles = list(Mesa.objects.filter(ocupada=False).order_by('idMesa').values('idMesa', 'capacidad'))

        return Response({
            'platillos_agrupados': platillos_agrupados,
            'pedido_existente': pedido_existente_data,
            'mesas_disponibles': mesas_disponibles,
            'inventario': inventario_actual,
            'recetas': recetas,
            'platillos_previos': platillos_previos,
            'empleado': {
                'nombre': request.user.nombre,
                'apellido': request.user.apellido,
                'rol': request.user.rol
            }
        }, status=status.HTTP_200_OK)

    def post(self, request, pedido_id=None):
        if request.user.rol != "Mesero":
            return Response({"error": "Acceso denegado."}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        cliente_data = data.get('cliente', {})
        nombre_cliente = cliente_data.get('nombre_cliente')
        telefono_cliente = cliente_data.get('telefono_cliente') or None
        correo_cliente = cliente_data.get('correo_cliente')
        tipo_cliente = cliente_data.get('tipo_cliente')
        identificacion_cliente = cliente_data.get('identificacion_cliente')
        
        id_mesa_seleccionada = data.get('mesa')
        productos_req = data.get('productos', [])

        if not nombre_cliente:
            return Response({'error': 'El nombre del cliente es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if tipo_cliente not in ["Persona", "Empresa"]:
            return Response(
                {'error': 'El tipo de cliente es inválido. Debe ser "Persona" o "Empresa".'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if tipo_cliente == "Empresa":
            if not identificacion_cliente or not str(identificacion_cliente).strip():
                return Response(
                    {'error': 'La identificación (RUC) es obligatoria para clientes de tipo "Empresa".'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        productos_a_registrar = {
            item['idProductoMenu']: int(item['cantidad']) 
            for item in productos_req 
            if int(item.get('cantidad', 0)) > 0
        }

        if not productos_a_registrar and not pedido_id:
            return Response({'error': 'Debe seleccionar al menos un platillo para registrar un nuevo pedido.'}, status=status.HTTP_400_BAD_REQUEST)

        id_pedido_a_usar = pedido_id
        cliente_a_usar_id = None
        mesa_asignada_obj = None

        try:
            with transaction.atomic():
                if pedido_id:
                    pedido_obj = get_object_or_404(Pedido, pk=pedido_id)
                    mesa_actual = pedido_obj.idMesa

                    if str(id_mesa_seleccionada) != str(mesa_actual.idMesa if mesa_actual else 'ninguna'):
                        if mesa_actual:
                            mesa_actual.ocupada = False
                            mesa_actual.save()
                        
                        if id_mesa_seleccionada and id_mesa_seleccionada != 'ninguna':
                            mesa_asignada_obj = get_object_or_404(Mesa, pk=id_mesa_seleccionada)
                            mesa_asignada_obj.ocupada = True
                            mesa_asignada_obj.save()
                            pedido_obj.idMesa = mesa_asignada_obj
                        else:
                            pedido_obj.idMesa = None
                        
                        pedido_obj.save()
                else:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT "idCliente" FROM "Cliente" WHERE "nombre" = %s LIMIT 1;', [nombre_cliente])
                        cliente_existente = cursor.fetchone()
                        
                        if cliente_existente:
                            cliente_a_usar_id = cliente_existente[0]
                        else:
                            sql_insert_cliente = """
                                INSERT INTO "Cliente" ("nombre", "telefono", "correo", "tipoCliente", "identificacion")
                                VALUES (%s, %s, %s, %s, %s) RETURNING "idCliente";
                            """
                            cursor.execute(sql_insert_cliente, [
                                nombre_cliente, 
                                telefono_cliente, 
                                correo_cliente, 
                                tipo_cliente, 
                                identificacion_cliente
                            ])
                            cliente_a_usar_id = cursor.fetchone()[0]

                    mesa_id_para_sql = None
                    if id_mesa_seleccionada and id_mesa_seleccionada != 'ninguna':
                        mesa_asignada_obj = get_object_or_404(Mesa, pk=id_mesa_seleccionada)
                        mesa_asignada_obj.ocupada = True
                        mesa_asignada_obj.save()
                        mesa_id_para_sql = mesa_asignada_obj.idMesa

                    with connection.cursor() as cursor:
                        sql_insert_pedido = """
                            INSERT INTO "Pedido" ("idCliente_id", "idMesa_id", "montoTotal", "fecha", "estadoDePago", "estado_factura")
                            VALUES (%s, %s, %s, NOW(), False, 'VIGENTE') RETURNING "idPedido";
                        """
                        cursor.execute(sql_insert_pedido, [cliente_a_usar_id, mesa_id_para_sql, 0.00])
                        id_pedido_a_usar = cursor.fetchone()[0]
                        
                        sql_insert_empleado_pedido = """
                            INSERT INTO "Empleado_Pedido" ("idEmpleado_id", "idPedido_id", "fechaAsignacion")
                            VALUES (%s, %s, NOW());
                        """
                        cursor.execute(sql_insert_empleado_pedido, [request.user.idEmpleado, id_pedido_a_usar])

                ingredientes_requeridos = {}
                if productos_a_registrar:
                    with connection.cursor() as cursor:
                        for producto_id, cantidad_pedido in productos_a_registrar.items():
                            cursor.execute('SELECT "idArticuloInventario_id", "cantidad_usada" FROM "ProductoMenu_ArticuloInventario" WHERE "idProductoMenu_id" = %s;', [producto_id])
                            
                            cantidad_pedido_decimal = Decimal(str(cantidad_pedido))
                            for id_ingrediente, cantidad_usada in cursor.fetchall():
                                cantidad_usada_decimal = Decimal(str(cantidad_usada))
                                ingredientes_requeridos[id_ingrediente] = ingredientes_requeridos.get(id_ingrediente, Decimal('0.00')) + (cantidad_usada_decimal * cantidad_pedido_decimal)

                        for id_ingrediente, cantidad_requerida in ingredientes_requeridos.items():
                            cursor.execute('SELECT "stock", "nombre" FROM "ArticuloInventario" WHERE "idArticuloInventario" = %s;', [id_ingrediente])
                            stock_data = cursor.fetchone()
                            if stock_data:
                                stock_decimal, nombre_ingrediente = Decimal(str(stock_data[0])), stock_data[1]
                                if cantidad_requerida > stock_decimal:
                                    raise ValueError(f"Stock insuficiente para '{nombre_ingrediente}'. Requerido: {cantidad_requerida:.2f}, Disponible: {stock_decimal:.2f}.")

                items_registrados = 0
                all_menu_objs = ProductoMenu.objects.filter(idProductoMenu__in=productos_a_registrar.keys())
                
                for producto_id, cantidad in productos_a_registrar.items():
                    productoMenu = next((p for p in all_menu_objs if p.idProductoMenu == producto_id), None)
                    
                    if productoMenu and cantidad > 0:
                        with connection.cursor() as cursor:
                            estado_inicial = 'Listo' if getattr(productoMenu, 'tiempoPreparacion', 0) == 0 else 'Registrado'

                            sql_insert_detalle = """
                                INSERT INTO "Pedido_ProductoMenu" ("idPedido_id", "idProductoMenu_id", "cantidad", "estado")
                                VALUES (%s, %s, %s, %s);
                            """
                            cursor.execute(sql_insert_detalle, [id_pedido_a_usar, productoMenu.idProductoMenu, cantidad, estado_inicial])
                            
                            cursor.execute('SELECT "idArticuloInventario_id", "cantidad_usada" FROM "ProductoMenu_ArticuloInventario" WHERE "idProductoMenu_id" = %s;', [productoMenu.idProductoMenu])
                            for id_ingrediente, cantidad_usada in cursor.fetchall():
                                cantidad_a_restar = Decimal(str(cantidad_usada)) * Decimal(str(cantidad))
                                cursor.execute('UPDATE "ArticuloInventario" SET "stock" = "stock" - %s WHERE "idArticuloInventario" = %s;', [cantidad_a_restar, id_ingrediente])

                        items_registrados += cantidad

                if items_registrados == 0 and not pedido_id:
                    with connection.cursor() as cursor:
                        cursor.execute('DELETE FROM "Pedido" WHERE "idPedido" = %s;', [id_pedido_a_usar])
                    if mesa_asignada_obj:
                        mesa_asignada_obj.ocupada = False
                        mesa_asignada_obj.save()
                    
                    return Response({'error': "Debe seleccionar al menos un platillo para registrar el pedido."}, status=status.HTTP_400_BAD_REQUEST)

            # --- SEPARACIÓN DE AUDITORÍA (Creación vs Modificación) ---
            if pedido_id:
                registrar_auditoria(request, 'Pedidos', 'Modificación', f"Se agregaron platillos a la orden existente N°{id_pedido_a_usar}.", sucursal_afectada_id=obtener_sucursal_contexto(request))
            else:
                registrar_auditoria(request, 'Pedidos', 'Creación', f"Se registró el nuevo Pedido N°{id_pedido_a_usar}.", sucursal_afectada_id=obtener_sucursal_contexto(request))

            return Response({
                "status": "success",
                "message": f"Pedido N°{id_pedido_a_usar} procesado con éxito.",
                "idPedido": id_pedido_a_usar
            }, status=status.HTTP_201_CREATED if not pedido_id else status.HTTP_200_OK)

        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Ocurrió un error interno: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ---------------------------- VISTAS DE SUCURSALES Y AUDITORÍA ----------------------------
class SetSucursalActivaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sucursal_id = request.data.get('sucursal_id')
        request.session['sucursal_activa_id'] = sucursal_id
        
        # --- MEJORA PARA LA AUDITORÍA ---
        nombre_vista = "Todas las sucursales"
        if sucursal_id and str(sucursal_id) != 'todas':
            sucursal = Sucursal.objects.filter(pk=sucursal_id).first()
            if sucursal:
                nombre_vista = sucursal.nombre_comercial
                
        registrar_auditoria(
            request, 
            'Sistema', 
            'Cambio de Vista', 
            f"El administrador cambió la vista en el panel a: {nombre_vista}."
        )
        
        return Response({"status": "success", "mensaje": "Sucursal actualizada"})


class AuditoriaGeneralAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.rol != 'Administrador':
            return Response(
                {"error": "No tienes permisos para visualizar la auditoría."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        auditoria = AuditoriaGeneral.objects.all().order_by('-fecha_accion')

        if request.user.sucursal_id:
            auditoria = auditoria.filter(sucursal_id=request.user.sucursal_id)
        else:
            sucursal_filtro = obtener_sucursal_contexto(request)
            if sucursal_filtro:
                auditoria = auditoria.filter(sucursal_id=sucursal_filtro)

        serializer = AuditoriaGeneralSerializer(auditoria, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SucursalAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SucursalSerializer
    queryset = Sucursal.objects.all().order_by('idSucursal')

    def perform_create(self, serializer):
        # Medida de seguridad extra
        if self.request.user.rol != 'Administrador' or self.request.user.sucursal_id:
            raise serializers.ValidationError({"error": "Solo el Administrador Global puede crear sucursales."})
        
        sucursal = serializer.save()
        
        # CORRECCIÓN: Inyectamos el ID de la sucursal recién creada
        registrar_auditoria(
            self.request, 
            'Sucursales', 
            'Creación', 
            f"Se registró la nueva sucursal '{sucursal.nombre_comercial}'.",
            sucursal_afectada_id=sucursal.idSucursal
        )

    def perform_update(self, serializer):
        sucursal = serializer.save()
        
        # CORRECCIÓN: Inyectamos el ID de la sucursal que se está editando
        registrar_auditoria(
            self.request, 
            'Sucursales', 
            'Actualización', 
            f"Se actualizaron los datos de la sucursal '{sucursal.nombre_comercial}'.",
            sucursal_afectada_id=sucursal.idSucursal
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        nombre = instance.nombre_comercial
        suc_id = instance.idSucursal # Guardamos el ID antes de eliminar
        
        # Bloqueo: No eliminar la sucursal si el usuario está actualmente "parado" sobre ella en el navbar
        if str(request.session.get('sucursal_activa_id')) == str(instance.idSucursal):
             return Response({"error": "No puedes eliminar una sucursal mientras la tienes activa en el menú superior."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance.delete()
            # CORRECCIÓN: Inyectamos el ID afectado
            registrar_auditoria(
                request, 
                'Sucursales', 
                'Eliminación', 
                f"Se eliminó permanentemente la sucursal '{nombre}'.",
                sucursal_afectada_id=suc_id
            )
            return Response({"message": f'La sucursal "{nombre}" ha sido eliminada permanentemente.'}, status=status.HTTP_200_OK)
        
        except ProtectedError:
            # Si ya tiene mesas, empleados o pedidos, solo la desactivamos
            instance.is_active = False
            instance.save()
            
            # CORRECCIÓN: Inyectamos el ID afectado
            registrar_auditoria(
                request, 
                'Sucursales', 
                'Desactivación', 
                f"La sucursal '{nombre}' fue desactivada por tener registros asociados.",
                sucursal_afectada_id=suc_id
            )
            return Response({"warning": f'La sucursal "{nombre}" tiene registros asociados. Ha sido desactivada para preservar la historia.'}, status=status.HTTP_200_OK)

class SolicitarRecuperacionAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        correo = request.data.get('correo', '').strip()
        if not correo:
            return Response({'error': 'El correo es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

        empleado = Empleado.objects.filter(correo=correo, is_active=True).first()

        if empleado:
            uid = urlsafe_base64_encode(force_bytes(empleado.pk))
            token = default_token_generator.make_token(empleado)
            dominio = request.get_host()
            enlace = f"http://{dominio}/reset-password/{uid}/{token}/"

            # Renderizamos el HTML elegante
            html_content = render_to_string('He_Sai_Mali/emails/recuperacion.html', {
                'nombre': empleado.nombre,
                'enlace': enlace
            })
            text_content = strip_tags(html_content)

            try:
                email = EmailMultiAlternatives(
                    'Restablecer Contraseña - He Sai Mali',
                    text_content,
                    settings.EMAIL_HOST_USER,
                    [empleado.correo]
                )
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)

                # Auditoría manual forzando la identidad del empleado (porque no hay sesión activa)
                ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
                if ip_address: ip_address = ip_address.split(',')[0]
                
                AuditoriaGeneral.objects.create(
                    empleado_id=empleado.idEmpleado,
                    usuario_nombre=f"{empleado.nombre} {empleado.apellido}",
                    rol=empleado.rol,
                    sucursal_id=empleado.sucursal_id,
                    modulo='Autenticación',
                    accion='Solicitud Recuperación',
                    detalles=f"Solicitó un enlace de recuperación al correo: {correo}",
                    ip_address=ip_address
                )
            except Exception as e:
                return Response({'error': 'Error de conexión con el servidor de correos.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Mensaje amigable y nada técnico
        return Response({
            'message': 'Si el correo está asociado a una cuenta, recibirás un enlace de recuperación en los próximos minutos.'
        }, status=status.HTTP_200_OK)


class RestablecerPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        nueva_password = request.data.get('password')

        if not all([uidb64, token, nueva_password]):
            return Response({'error': 'Faltan datos para procesar la solicitud.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validación backend de contraseña fuerte (10 chars, upper, lower, num, symbol)
        password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{10,}$'
        if not re.match(password_regex, nueva_password):
            return Response({'error': 'La contraseña no cumple con los requisitos mínimos de seguridad.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            empleado = Empleado.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, Empleado.DoesNotExist):
            empleado = None

        if empleado is not None and default_token_generator.check_token(empleado, token):
            empleado.set_password(nueva_password)
            empleado.save()

            # Auditoría manual al restablecer
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            if ip_address: ip_address = ip_address.split(',')[0]
            
            AuditoriaGeneral.objects.create(
                empleado_id=empleado.idEmpleado,
                usuario_nombre=f"{empleado.nombre} {empleado.apellido}",
                rol=empleado.rol,
                sucursal_id=empleado.sucursal_id,
                modulo='Autenticación',
                accion='Contraseña Restablecida',
                detalles=f"Restableció su contraseña con éxito mediante enlace de correo.",
                ip_address=ip_address
            )
            
            return Response({'message': 'Contraseña actualizada exitosamente. Redirigiendo...'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'El enlace es inválido o ya expiró. Por favor, solicita uno nuevo.'}, status=status.HTTP_400_BAD_REQUEST)
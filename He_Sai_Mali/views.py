from django.db import IntegrityError, connection, transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db.models import F, Sum, ProtectedError, FloatField, Max, Q
from itertools import groupby
from operator import attrgetter
from datetime import timedelta
from django.utils import timezone
from django.urls import reverse
from django.http import JsonResponse
import qrcode
from io import BytesIO
import base64
from decimal import Decimal
import re
import time
from datetime import datetime

# Importaciones para generar pdf
from django.contrib.staticfiles.finders import find
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.platypus.flowables import Flowable
from reportlab.lib import colors

# Estructura de tablas y decoradores
from .models import *
from .decorators import *

@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def main_registro_html(request):
    return render(request, 'He_Sai_Mali/registro.html')

# Vista principal (Bienvenida)
def main(request):
    return render(request, 'He_Sai_Mali/main.html')

# Vista para el login de los empleados
@never_cache
def login_view_html(request):
    if request.user.is_authenticated:
        # El usuario se autentica con la tabla Empleado, su rol se determina
        # al buscarlo en la tabla Empleado
        rol = (request.user.rol or '').strip().lower()
        # Redirige a una vista principal para cada tipo de empleado
        if rol == "administrador":
            return redirect('admin_dashboard')
        elif rol == "mesero":
            return redirect('pedidos')
        elif rol == "cocinero":
            return redirect('cocina')
    return render(request, 'He_Sai_Mali/login.html')

@user_passes_test(es_rol("Mesero"), login_url='login')
def facturar_pedido_html(request, pedido_id):
    return render(request, 'He_Sai_Mali/factura.html', {'pedido_id': pedido_id})

def calcular_monto_total(pedido_id):
    pedido = Pedido.objects.filter(pk=pedido_id).first()
    if pedido and pedido.montoTotal:
        return float(pedido.montoTotal)
    return 0.0

# Funcion para generar lineas en el PDF
class Line(Flowable):
    def __init__(self, width, height=0):
        Flowable.__init__(self)
        self.width = width
        self.height = height

    def draw(self):
        self.canv.line(0, self.height, self.width, self.height)

from reportlab.platypus import HRFlowable
# Funcion para generar PDF de la factura
def generar_pdf_factura(pedido_id):
    # 1. Obtener datos
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    # Asegúrate de que esta función esté disponible en tu archivo
    monto_total_sin_impuesto = calcular_monto_total(pedido_id) 
    monto_total_decimal = Decimal(str(monto_total_sin_impuesto))
    
    TASA_IMPUESTO = Decimal('0.15')
    subtotal = monto_total_decimal
    impuesto = monto_total_decimal * TASA_IMPUESTO
    total_con_impuesto = subtotal + impuesto
    cliente = pedido.idCliente 
    platillos_pedido = Pedido_ProductoMenu.objects.filter(idPedido=pedido).exclude(estado__in=['Merma', 'Anulado']).select_related('idProductoMenu')
    
    # --- Configuración del PDF ---
    response = HttpResponse(content_type='application/pdf')
    filename = f"factura_pedido_{pedido_id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos Personalizados
    style_center_h1 = ParagraphStyle(name='CenterH1', alignment=1, fontSize=18)
    style_center_h2 = ParagraphStyle(name='CenterH2', alignment=1, fontSize=14)
    style_details = styles['Normal'] 

    # Ancho utilizable
    PAGE_WIDTH = 6.5 * inch
    
    # --- 1. ENCABEZADO ---
    logo_path = find('He_Sai_Mali/logo.png') 
    LOGO_WIDTH = 0.8 * inch 
    LOGO_HEIGHT = 0.8 * inch
    
    header_data = []
    if logo_path:
        logo = Image(logo_path, width=LOGO_WIDTH, height=LOGO_HEIGHT)
        logo.hAlign = 'LEFT'
        header_data.append(logo)
    else:
        header_data.append(Paragraph("", styles['Normal'])) 

    titulo_bloque = [
        Paragraph("<b>Hê Sãî Mãlî</b>", style_center_h1),
        Spacer(1, 0.05 * inch),
        Paragraph("Factura de Pedido", style_center_h2),
    ]
    header_data.append(titulo_bloque)

    header_table = Table(data=[header_data], colWidths=[1.5 * inch, 5.0 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)

    # --- 2. LÍNEA SEPARADORA (Corregido con HRFlowable) ---
    story.append(HRFlowable(width=PAGE_WIDTH, thickness=1, color=colors.black))
    story.append(Spacer(1, 0.15 * inch))

    # --- 3. DETALLES ---
    detalle_texto = f"""
    <b>ID Pedido:</b> {pedido.idPedido}<br/>
    <b>Cliente:</b> {cliente.nombre} <br/>
    <b>Fecha:</b> {(pedido.fecha - timedelta(hours=6)).strftime('%d/%m/%Y %H:%M')}<br/>
    <b>Teléfono:</b> {cliente.telefono or 'N/A'}<br/>
    <b>Dirección:</b> {cliente.direccion or 'N/A'}<br/>
    <b>Método de Pago:</b> {pedido.metodoPago or 'N/A'}
    """
    if cliente.tipoCliente == "empresa":
        detalle_texto += f"<br/><b>RUC:</b> {cliente.identificacion}"

    story.append(Paragraph(detalle_texto, style_details))
    story.append(Spacer(1, 0.15 * inch))

    # --- 4. LÍNEA SEPARADORA ---
    story.append(HRFlowable(width=PAGE_WIDTH, thickness=1, color=colors.black))
    story.append(Spacer(1, 0.15 * inch))

    # --- 5. TABLA DE PRODUCTOS ---
    data = [['Producto', 'Cant.', 'Precio Unit.', 'Subtotal']]
    for item in platillos_pedido:
        nombre = item.idProductoMenu.nombre
        cantidad = str(item.cantidad)
        precio_unit = f"C${item.idProductoMenu.precio:.2f}"
        total_item = item.cantidad * item.idProductoMenu.precio
        total_item_str = f"C${total_item:.2f}"
        data.append([nombre, cantidad, precio_unit, total_item_str])

    table = Table(data, colWidths=[3*inch, 1*inch, 1*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black), 
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),      
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),    
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),     
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.1, colors.white),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.25 * inch))

    # --- 6. TOTALES ---
    totales_data = [
        ['Subtotal:', f"C${subtotal:.2f}"],
        [f"Impuesto (IVA {int(TASA_IMPUESTO * 100)}%):", f"C${impuesto:.2f}"],
    ]
    totales_table_1 = Table(totales_data, colWidths=[5*inch, 1.5*inch]) 
    totales_table_1.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
    ]))
    story.append(totales_table_1)
    
    story.append(Spacer(1, 0.05 * inch))
    
    total_final_data = [['Total a Pagar:', f"C${total_con_impuesto:.2f}"]]
    total_final_table = Table(total_final_data, colWidths=[5*inch, 1.5*inch])
    total_final_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.black), 
    ]))
    story.append(total_final_table)
    
    doc.build(story)
    return response

# Vista dedicada solo a generar y servir el archivo PDF
@user_passes_test(lambda u: u.rol == "Mesero" or u.rol == "Administrador", login_url='login')
def descargar_pdf_factura(request, pedido_id):
    try:
        return generar_pdf_factura(pedido_id)
    except Exception as e:
        messages.error(request, f"Error al generar PDF: {e}")
        return redirect(request.META.get('HTTP_REFERER', 'historial_facturas'))

# Vista para ver los pedidos activos
@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_mesero_html(request):
    return render(request, 'He_Sai_Mali/pedidos.html') 

# Vista para registrar nuevos pedidos y agregar productos a un pedido existente
@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_registrarpedido_html(request, pedido_id=None):
    return render(request, 'He_Sai_Mali/registrarpedido.html', {'pedido_id': pedido_id})

# Vista de la cocina
@never_cache
@user_passes_test(es_rol("Cocinero"), login_url='login')
def vista_cocinero_html(request):
    return render(request, 'He_Sai_Mali/cocina.html')

# Vistas para el control de los articulos del inventario
@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def admin_ingredientes_html(request):
    return render(request, 'He_Sai_Mali/admin_ingredientes.html')

# Vistas para el control de los productos del menu
@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def admin_platillos_html(request):
    return render(request, 'He_Sai_Mali/admin_platillos.html')

@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def admin_proveedores_html(request):
    return render(request, 'He_Sai_Mali/admin_proveedores.html')

# Vistas para el control de las mesas y ver disponibilidad de mesas en el caso del mesero
@never_cache
@user_passes_test(es_rol_y_administrador("Mesero"), login_url='login')
def admin_mesas_html(request):
    context = {
        'rol_empleado': request.user.rol,
    }
    return render(request, 'He_Sai_Mali/mesas.html', context)

# Vista del dashboard para el administrador
@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def admin_dashboard_html(request):
    return render(request, 'He_Sai_Mali/dashboard.html')

@user_passes_test(es_rol("Administrador"), login_url='login')
def generate_dashboard_pdf(request):
    TASA_IMPUESTO_FACTOR = 1.15
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    search_query = request.GET.get('search', '').strip()

    today = timezone.now().date()
    if not start_date_str:
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, today.day))
    else:
        start_date = timezone.make_aware(timezone.datetime.strptime(start_date_str, '%Y-%m-%d'))
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if not end_date_str:
        end_date = timezone.make_aware(timezone.datetime(today.year, today.month, today.day, 23, 59, 59))
    else:
        end_date = timezone.make_aware(timezone.datetime.strptime(end_date_str, '%Y-%m-%d'))
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    if start_date > end_date:
        # swap or set default
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, today.day))
        end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)

    date_filter = {
        'fecha__gte': start_date,
        'fecha__lte': end_date,
        'estadoDePago': True
    }

    if search_query:
        pedidos_periodo = Pedido.objects.filter(**date_filter)
        search_results = pedidos_periodo.filter(
            idCliente__nombre__icontains=search_query
        ).select_related('idCliente', 'idMesa').order_by('-fecha')
        search_results_count = search_results.count()
        if search_results_count > 0:
            pedidos_encontrados_ids = list(search_results.values_list('idPedido', flat=True))
            date_filter = {'idPedido__in': pedidos_encontrados_ids}
        else:
            date_filter = {'idPedido__in': []}

    if date_filter.get('idPedido__in') == []:
        total_sales = 0.00
        total_orders = 0
        pedidos_list = Pedido.objects.none()
    else:
        total_sales_agg = Pedido.objects.filter(**date_filter).aggregate(
            total=Sum(F('montoTotal') * TASA_IMPUESTO_FACTOR, output_field=FloatField())
        )
        total_sales = total_sales_agg['total'] or 0.00
        total_orders = Pedido.objects.filter(**date_filter).count()
        pedidos_list = Pedido.objects.filter(**date_filter).select_related('idCliente', 'idMesa').order_by('-fecha')

    total_mesas = Mesa.objects.count()
    platillos_en_menu = ProductoMenu.objects.filter(disponible=True).count()

    # Generación del PDF (similar a antes, pero usando start_date_str y end_date_str)
    response = HttpResponse(content_type='application/pdf')
    filename = f"dashboard_{start_date_str}_to_{end_date_str}"
    if search_query:
        clean_search = re.sub(r'[^a-zA-Z0-9]', '_', search_query)[:20]
        filename += f"_cliente_{clean_search}"
    filename += f"_{timezone.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    style_center_h1 = ParagraphStyle(name='CenterH1', alignment=1, fontSize=18)
    style_center_h2 = ParagraphStyle(name='CenterH2', alignment=1, fontSize=14)
    PAGE_WIDTH = 6.5 * inch

    # Encabezado...
    logo_path = find('He_Sai_Mali/logo.png')
    LOGO_WIDTH = 0.8 * inch
    LOGO_HEIGHT = 0.8 * inch
    header_data = []
    if logo_path:
        logo = Image(logo_path, width=LOGO_WIDTH, height=LOGO_HEIGHT)
        logo.hAlign = 'LEFT'
        header_data.append(logo)
    else:
        header_data.append(Paragraph("", styles['Normal']))
    titulo_bloque = [
        Paragraph("<b>Hê Sãî Mãlî</b>", style_center_h1),
        Spacer(1, 0.05 * inch),
        Paragraph("Reporte de ventas", style_center_h2),
    ]
    header_data.append(titulo_bloque)
    header_table = Table(data=[header_data], colWidths=[1.5 * inch, 5.0 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Line(PAGE_WIDTH, 1))
    story.append(Spacer(1, 0.15 * inch))

    tiempo_generacion = timezone.localtime(timezone.now()) - timedelta(hours=6)
    story.append(Paragraph(f"Generado el: <b>{tiempo_generacion.strftime('%d/%m/%Y %H:%M:%S')}</b>", styles['Normal']))
    story.append(Paragraph(f"Período: <b>{start_date_str} al {end_date_str}</b>", styles['Normal']))
    if search_query:
        story.append(Paragraph(f"Cliente: <b>{search_query}</b>", styles['Normal']))
        story.append(Paragraph(f"Pedidos encontrados: <b>{total_orders}</b>", styles['Normal']))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(f"<b>Métricas Clave</b>", styles['h2']))
    if search_query:
        story.append(Paragraph(f"<i>Filtrado por cliente: '{search_query}'</i>", styles['Normal']))
    story.append(Spacer(1, 0.1 * inch))

    metrics_data = [
        ['Ventas Totales:', f"C${total_sales:.2f}", 'Pedidos Facturados:', f"{total_orders}"],
        ['Mesas Registradas:', f"{total_mesas}", 'Productos en el Menú:', f"{platillos_en_menu}"],
    ]
    metrics_table = Table(metrics_data, colWidths=[2 * inch, 1.25 * inch, 1.5 * inch, 1.75 * inch])
    metrics_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
        ('RIGHTPADDING', (3, 0), (3, -1), 0),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("<b>Listado Detallado de Pedidos Facturados</b>", styles['h2']))
    story.append(Spacer(1, 0.1 * inch))

    if pedidos_list.exists():
        pedidos_data = [['ID', 'Fecha', 'Cliente', 'Mesa', 'Total']]
        for pedido in pedidos_list:
            cliente_nombre = pedido.idCliente.nombre if pedido.idCliente else "N/A"
            mesa_label = f"Mesa {pedido.idMesa.idMesa}" if pedido.idMesa else "Sin Mesa"
            total_con_iva = Decimal(str(pedido.montoTotal)) * Decimal(str(TASA_IMPUESTO_FACTOR))
            pedidos_data.append([
                str(pedido.idPedido),
                pedido.fecha.strftime('%d/%m/%Y %H:%M'),
                cliente_nombre,
                mesa_label,
                f"C${total_con_iva:.2f}",
            ])
        pedidos_table = Table(pedidos_data, colWidths=[0.75*inch, 1.75*inch, 1.75*inch, 1.25*inch, 1*inch])
        pedidos_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#41444a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (3, -1), 'LEFT'),
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ]))
        story.append(pedidos_table)
    else:
        mensaje = "No hay pedidos facturados en el periodo seleccionado"
        if search_query:
            mensaje += f" para el cliente '{search_query}'"
        mensaje += "."
        story.append(Paragraph(mensaje, styles['Normal']))

    doc.build(story)
    return response

# Vista para ver los QR asignados a cada mesa
def vista_qr_mesas(request, mesa_id):
    mesa = get_object_or_404(Mesa, idMesa=mesa_id)
    
    # 2. Construir la URL que contendrá el QR (la del temporizador)
    # 'temporizador_mesa' es el name de la ruta de destino del QR.
    url_to_embed = request.build_absolute_uri(reverse('temporizador_mesa', args=[mesa.idMesa]))
    qr_data = url_to_embed
    
    # 3. Generar el código QR y codificar en base64
    qr_img = qrcode.make(qr_data)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # 4. Preparar el contexto para la plantilla (como una lista de 1 elemento)
    mesa_con_qr = {
        'idMesa': mesa.idMesa,
        'nombre': f'Mesa {mesa.idMesa}',
        'qr_data': f'data:image/png;base64,{qr_base64}',
    }
    
    if request.user.is_authenticated:
        logout(request)

    # 5. Renderizar la plantilla
    return render(request, 'He_Sai_Mali/qr_mesas.html', {
        'mesas': [mesa_con_qr], # Se pasa una lista con un solo elemento para compatibilidad con el template
        'titulo': f'Código QR Mesa {mesa.idMesa}' # Título dinámico para la plantilla
    })

def temporizador_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, idMesa=mesa_id)
    
    latest_pedido = Pedido.objects.filter(
        idMesa=mesa,
        estado_factura='VIGENTE' 
    ).order_by('idPedido').last()

    remaining_seconds = 0
    tiempo_total_segundos = 0
    fase = 'ANTES'  # Fases posibles: ANTES, DURANTE, SERVIDO, COMPLETADO
    has_active_pedido = False
    current_ts = int(time.time()) # Timestamp actual absoluto para cálculos limpios

    if latest_pedido:
        ready_key = f"pedido_ready_{latest_pedido.idPedido}"
        
        # REGLA 5: Solo aplicamos ventana de gracia si ya fue marcado como "Listo" (SERVIDO)
        if ready_key in request.session and (current_ts - request.session[ready_key]) > 300:
            fase = 'ANTES'
            remaining_seconds = 0
            tiempo_total_segundos = 0
            has_active_pedido = False
        else:
            # Obtener solo productos válidos
            items_validos = Pedido_ProductoMenu.objects.filter(
                idPedido=latest_pedido.idPedido
            ).exclude(
                estado__in=['Anulado', 'Merma']
            )
            
            agregados = items_validos.aggregate(
                tiempo_maximo=Max('idProductoMenu__tiempoPreparacion'),
                total_quantity=Sum('cantidad')
            )
            
            tiempo_base_segundos = agregados.get('tiempo_maximo') or 0
            total_quantity = agregados.get('total_quantity') or 0

            if total_quantity > 0:
                # REGLA 1: Verificar si TODOS los productos válidos pasaron a 'Listo' o 'Entregado'
                items_no_listos = items_validos.exclude(estado__in=['Listo', 'Servido', 'Facturado'])
                todos_listos = not items_no_listos.exists()

                # Tiempos de preparación teóricos
                tiempo_logistica_segundos = total_quantity * 45
                tiempo_servicio_segundos = 60
                tiempo_total_segundos = tiempo_base_segundos + tiempo_logistica_segundos + tiempo_servicio_segundos

                # --- EL CAMBIO ESTÁ AQUÍ ---
                # Como la BD ya guarda la hora perfecta, simplemente calculamos el tiempo final
                # y le restamos la hora actual del sistema operativo (timezone.now() directo).
                end_time = latest_pedido.fecha + timedelta(seconds=tiempo_total_segundos)
                time_difference = end_time - timezone.now()
                remaining_seconds_teorico = int(time_difference.total_seconds())
                # ---------------------------

                # Evaluación de escenarios en tiempo real
                if todos_listos:
                    # El pedido se terminó. AQUÍ inicia la ventana de gracia.
                    if ready_key not in request.session:
                        request.session[ready_key] = current_ts
                        request.session.modified = True
                    
                    elapsed_since_ready = current_ts - request.session[ready_key]
                    remaining_seconds = max(0, 300 - elapsed_since_ready)
                    tiempo_total_segundos = 300  # Redefinimos el total del ciclo a 5 min para la interfaz
                    
                    if remaining_seconds == 0:
                        fase = 'ANTES'  # REGLA 4: Pasados los 5 minutos de estar SERVIDO, vuelve a ANTES
                        has_active_pedido = False
                    else:
                        fase = 'SERVIDO'
                        has_active_pedido = True
                else:
                    # Cuenta regresiva normal en proceso
                    remaining_seconds = max(0, remaining_seconds_teorico)
                    
                    if remaining_seconds == 0:
                        # El tiempo se agotó de forma natural pero los platillos NO están listos.
                        fase = 'COMPLETADO'
                        has_active_pedido = True 
                        tiempo_total_segundos = 0
                        remaining_seconds = 0
                    else:
                        fase = 'DURANTE'
                        has_active_pedido = True

    context = {
        'mesa_id': mesa_id,
        'remaining_seconds': remaining_seconds,
        'has_active_pedido': has_active_pedido,
        'tiempo_total_segundos': tiempo_total_segundos,
        'fase': fase
    }
    
    if request.GET.get('format') == 'json':
        return JsonResponse(context)
        
    return render(request, 'He_Sai_Mali/temporizador.html', context)

# Vista para administrar los empleados
@never_cache
@user_passes_test(es_rol("Administrador"), login_url='login')
def admin_empleados_html(request):
    context = {
        # Roles estáticos que necesita el formulario desplegable en el HTML
        'roles_disponibles': ['Administrador', 'Mesero', 'Cocinero'],
    }
    
    return render(request, 'He_Sai_Mali/admin_empleados.html', context)

# Funcionalidad para ver el historial de facturas (pedidos) en el dashboard del administrador
@user_passes_test(es_rol("Administrador"), login_url='login')
def historial_facturas_html(request):
    return render(request, 'He_Sai_Mali/historial_facturas.html')

# Funcionaliad para cerra sesion
@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
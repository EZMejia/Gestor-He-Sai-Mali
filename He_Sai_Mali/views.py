from django.db import connection, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test

from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db.models import F, Sum, Count

from django.http import Http404

from datetime import timedelta
import json

from django.utils import timezone
from django.urls import reverse

import qrcode
from io import BytesIO
import base64

from decimal import Decimal

from django.db.models import ProtectedError

from .models import *

import re

from .decorators import es_rol

# Create your views here.
def main(request):
    return render(request, 'He_Sai_Mali/main.html')

def origen(request):
    return render(request, 'He_Sai_Mali/origen.html')

@never_cache
def registro(request):
    if request.method == 'POST':
        # --- Obtener datos ---
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        telefono = request.POST.get('telefono', '').strip() or None
        correo = request.POST.get('correo', '').strip()
        cedula = request.POST.get('cedula', '').strip()
        rol = request.POST.get('rol', '').strip()
        contrasena1 = request.POST.get('contrasena1')
        contrasena2 = request.POST.get('contrasena2')

        # --- Validaciones ---
        errores = []

        if contrasena1 != contrasena2:
            errores.append("Las contraseñas no coinciden.")
        with connection.cursor() as cursor:
            sql_select_correo = """SELECT COUNT(*) FROM "Empleado" WHERE "correo" = %s"""
            cursor.execute(sql_select_correo, [correo])
            if cursor.fetchone()[0] > 0:
                errores.append("Este correo ya está registrado.")

        # --- Generar Usuario ---
        usuario = None
        if nombre and apellido and rol:
            def primeras_dos(palabra):
                return re.sub(r'[^a-zA-Z]', '', palabra).lower()[:2]
            base = primeras_dos(nombre) + primeras_dos(apellido) + rol.capitalize() + "HSM"
            usuario = base
            contador = 1
            while True:
                with connection.cursor() as cursor:
                    sql_select_usuario = """SELECT COUNT(*) FROM "Empleado" WHERE "usuario" = %s"""
                    cursor.execute(sql_select_usuario, [usuario])
                    
                    if cursor.fetchone()[0] == 0:
                        # El nombre de usuario está disponible
                        break
                    
                    # El nombre de usuario existe, intentamos con un contador
                    usuario = f"{base}{contador}"
                    contador += 1
        else:
            errores.append("Nombre, Apellido y Rol son necesarios para generar el usuario.")

        # --- Si hay errores ---
        if errores:
            return render(request, 'He_Sai_Mali/registro.html', {
                'errores': errores,
                'valores': request.POST
            })

        # --- Crear empleado ---
        contrasena_hash = make_password(contrasena1)

        with connection.cursor() as cursor:
            sql_insert_empleado = """
                INSERT INTO "Empleado" ("nombre", "apellido", "telefono", "correo", "cedula", "rol", "usuario", "password", "is_active", "is_staff","is_superuser", "date_joined")
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, FALSE, NOW() AT TIME ZONE 'CST');
            """
            cursor.execute(sql_insert_empleado, [
                nombre,
                apellido,
                telefono,
                correo,
                cedula,
                rol,
                usuario,
                contrasena_hash
            ])
        
            # Si el INSERT fue exitoso
            return redirect('login')

    return render(request, 'He_Sai_Mali/registro.html')

@never_cache
def login_view(request):
    if request.user.is_authenticated:
        # El usuario se autentica con la tabla Empleado, su rol se determina
        # al buscarlo en la tabla Empleado
        rol = (request.user.rol or '').strip().lower()
        if rol == "administrador":
            return redirect('pedidos')
        elif rol == "mesero":
            return redirect('pedidos')
        elif rol == "cocinero":
            return redirect('cocina')
    
    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        contrasena = request.POST.get('contrasena')

        if not usuario or not contrasena:
            messages.error(request, 'Usuario y contraseña son obligatorios.')
        else:
            user = authenticate(request, username=usuario, password=contrasena)
            if user is not None:
                login(request, user)
                rol = (user.rol or '').strip().lower()
                if rol == "administrador":
                    return redirect('pedidos')
                elif rol == "mesero":
                    return redirect('pedidos')
                elif rol == "cocinero":
                    return redirect('cocina')
                else:
                    return redirect('pedidos')
            else:
                messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'He_Sai_Mali/login.html')

# --- Botones de pedido ---

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def cambiar_estado_platillo(request, pedido_platillo_id):
    """Cambia el estado de un ProductoMenu dentro de un Pedido (Pedido_ProductoMenu)."""
    # Usamos get_object_or_404 para manejar el caso de ID no encontrado
    pedido_ProductoMenu = get_object_or_404(Pedido_ProductoMenu, pk=pedido_platillo_id)
    
    current_state = pedido_ProductoMenu.estado
    next_state = None
    
    # Lógica de transición de estado
    if current_state == 'Registrado':
        next_state = 'Listo'
    elif current_state == 'Listo':
        next_state = 'Servido'
    
    if next_state:
        with connection.cursor() as cursor:
            sql_update_estado = """
                UPDATE "Pedido_ProductoMenu"
                SET "estado" = %s
                WHERE "idPedido_ProductoMenu" = %s;
            """
            cursor.execute(sql_update_estado, [next_state, pedido_platillo_id])

        messages.success(request, f"Estado de {pedido_ProductoMenu.idProductoMenu.nombre} cambiado a '{next_state}'.")
    else:
        messages.info(request, f"El estado de {pedido_ProductoMenu.idProductoMenu.nombre} es '{current_state}', no se puede cambiar.")

    # Redirigir a la vista principal de pedidos
    return redirect('pedidos')

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def facturar_pedido(request, pedido_id):
    """
    Cambia el estado de *todos* los ProductoMenu de un pedido a 'Facturado'
    solo si todos los ProductoMenu no facturados están en estado 'Servido'.
    
    LÓGICA DE MESA IMPLEMENTADA: Libera la mesa si el pedido tiene una asignada.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    
    # 1. Contar ProductoMenu pendientes de facturar y sus estados
    items_pendientes = Pedido_ProductoMenu.objects.filter(idPedido=pedido).exclude(estado='Facturado')
    items_facturables = items_pendientes.count()
    items_servidos = items_pendientes.filter(estado='Servido').count()

    if items_facturables > 0 and items_facturables == items_servidos:
        if request.method == 'POST':
            metodo_pago = request.POST.get('metodo_pago')
            if not metodo_pago:
                messages.error(request, "Debe seleccionar un método de pago.")
                # Si el POST falla, volvemos a mostrar el formulario.
                # Se necesita la función calcular_monto_total (ver nota en views.py)
                return render(request, 'He_Sai_Mali/solicitar_pago.html', {
                    'pedido': pedido, 
                    'monto_total': calcular_monto_total(pedido_id),
                    'metodos': ['Efectivo', 'Tarjeta', 'Transferencia']
                })

            try:
                with transaction.atomic():
                    pedido.metodoPago = metodo_pago
                    pedido.estadoDePago = 0 # Asegurar que esté pendiente
                    pedido.save()
                
                return redirect('mostrar_factura', pedido_id=pedido.idPedido)

            except Exception as e:
                print(e)
                messages.error(request, f"Error al registrar el método de pago: {e}")
                return redirect('pedidos')
        
        # 2. Manejo del GET (Mostrar Formulario de Selección de Pago)
        # Nota: Se debe definir la función auxiliar calcular_monto_total en views.py.
        return render(request, 'He_Sai_Mali/solicitar_pago.html', {
            'pedido': pedido, 
            'monto_total': calcular_monto_total(pedido_id),
            'metodos': ['Efectivo', 'Tarjeta', 'Transferencia']
        })

def calcular_monto_total(pedido_id):
    """Función auxiliar para calcular el monto total de un pedido."""
    with connection.cursor() as cursor:
        sql_total = """
            SELECT SUM(pp."cantidad" * pl."precio") AS "montoTotal"
            FROM "Pedido" p
            JOIN "Pedido_ProductoMenu" pp ON pp."idPedido_id" = p."idPedido"
            JOIN "ProductoMenu" pl ON pl."idProductoMenu" = pp."idProductoMenu_id"
            WHERE p."idPedido" = %s;
        """
        cursor.execute(sql_total, [pedido_id])
        return cursor.fetchone()[0] or 0.0
    
@user_passes_test(es_rol("Mesero"), login_url='login')
def mostrar_factura(request, pedido_id):
    """
    Genera y muestra la factura con los detalles y los botones de 'Cancelar' y 'Pagada'.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    # 1. Obtener el monto total usando la función auxiliar
    monto_total = calcular_monto_total(pedido_id)

    # 2. Obtener el detalle de los platillos del pedido
    platillos_pedido = Pedido_ProductoMenu.objects.filter(
        idPedido=pedido
    ).select_related('idProductoMenu')
    
    TASA_IMPUESTO = Decimal('0.15') # 15% de impuesto (1 + 0.15)
    monto_total_decimal = Decimal(str(monto_total)) # Asegurar que sea Decimal

    # 3. Cálculos de subtotales e impuestos (ejemplo con 15% de impuesto)
    if monto_total_decimal:
        # CORRECCIÓN: Dividir Decimal entre Decimal (o float si TASA_IMPUESTO se dejara en 1.15)
        subtotal = monto_total_decimal
        impuesto = monto_total_decimal * TASA_IMPUESTO
    else:
        subtotal = Decimal('0.00')
        impuesto = Decimal('0.00')
    
    # Obtener datos del cliente (Asumo que el modelo Cliente existe)
    cliente = pedido.idCliente

    context = {
        'pedido': pedido,
        'cliente': cliente,
        'platillos_pedido': platillos_pedido,
        'monto_total': monto_total + impuesto,
        'subtotal': subtotal,
        'impuesto': impuesto,
        'estado_pago_texto': 'Pagada' if pedido.estadoDePago == 1 else 'Pendiente'
    }
    
    # Renderizar la plantilla de la factura
    return render(request, 'He_Sai_Mali/factura.html', context)

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def pagar_factura(request, pedido_id):
    """
    Marca la factura como pagada (estadoDePago=1), actualiza el estado de platillos a 'Facturado' y libera la mesa.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    if pedido.estadoDePago == 1:
        messages.info(request, f"El Pedido N°{pedido.idPedido} ya ha sido marcado como pagado.")
        return redirect('pedidos')

    try:
        with transaction.atomic():
            # 1. Actualizar el estado de pago del Pedido
            pedido.estadoDePago = 1 # Marcar como pagada
            pedido.save()
            
            # 2. Actualizar el estado de *todos* los Pedido_ProductoMenu a 'Facturado'
            with connection.cursor() as cursor:
                sql_update_facturar = """
                    UPDATE "Pedido_ProductoMenu"
                    SET "estado" = 'Facturado'
                    WHERE "idPedido_id" = %s AND "estado" IN ('Registrado', 'Listo', 'Servido');
                """
                cursor.execute(sql_update_facturar, [pedido_id])
                    
            # 3. Liberar la mesa si hay una asignada
            if pedido.idMesa:
                try:
                    mesa_a_liberar = pedido.idMesa
                    mesa_a_liberar.ocupada = False
                    mesa_a_liberar.save()
                    messages.info(request, f"Mesa N°{mesa_a_liberar.idMesa} liberada exitosamente.")
                except Exception as e:
                    messages.warning(request, f"Advertencia: No se pudo liberar la mesa del pedido. Error: {e}")

        messages.success(request, f"Pago registrado exitosamente para el Pedido N°{pedido.idPedido}. Factura completada.")
        
    except Exception as e:
        messages.error(request, f"Error al registrar el pago: {e}")

    return redirect('pedidos')

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def eliminar_pedido(request, pedido_id):
    """
    Elimina un Pedido si *todos* sus ProductoMenu están aún en estado 'Registrado'.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    # 1. Verificar si todos los ProductoMenu están en 'Registrado'
    # Contamos cuántos NO están en 'Registrado'
    with connection.cursor() as cursor:
        # 1. Verificar si todos los ProductoMenu están en 'Registrado'
        # Contamos cuántos NO están en 'Registrado'
        sql_items_no_registrados = """
            SELECT COUNT(*) FROM "Pedido_ProductoMenu" 
            WHERE "idPedido_id" = %s AND "estado" NOT IN ('Registrado');
        """
        cursor.execute(sql_items_no_registrados, [pedido_id])
        items_no_registrados = cursor.fetchone()[0]
    
    if items_no_registrados == 0:
        # Si la cuenta es 0, todos están en 'Registrado'
        with transaction.atomic():           
            with connection.cursor() as cursor:
                sql_delete_detalles = """
                    DELETE FROM "Pedido_ProductoMenu" 
                    WHERE "idPedido_id" = %s;
                """
                cursor.execute(sql_delete_detalles, [pedido_id])

                sql_delete_empleado_pedido = """
                    DELETE FROM "Empleado_Pedido" 
                    WHERE "idPedido_id" = %s;
                """
                cursor.execute(sql_delete_empleado_pedido, [pedido_id])

                sql_delete_pedido = """
                    DELETE FROM "Pedido" 
                    WHERE "idPedido" = %s;
                """
                cursor.execute(sql_delete_pedido, [pedido_id])

            if pedido.idMesa:
                pedido.idMesa.ocupada = False
                pedido.idMesa.save()
                
            messages.success(request, f"Pedido N°{pedido_id} eliminado exitosamente.")
    else:
        messages.error(request, f"No se puede eliminar el Pedido N°{pedido_id}. Algunos platillos ya han cambiado de estado (Listo/Servido/Facturado).")

    return redirect('pedidos')

# --- Fin de Vistas de Acción ---

@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_mesero(request):
    """Muestra la cola de pedidos activos y obtiene el estado de facturación/registro para los botones."""
    
    # 1. Obtener los pedidos que tienen al menos un ProductoMenu no facturado
    cola_pedidos = Pedido.objects.raw("""
        SELECT p."idPedido", p."fecha", p."metodoPago", c."nombre",
        SUM(pp."cantidad" * pl."precio") AS "montoTotal"
        FROM "Pedido" p
        JOIN "Cliente" c ON c."idCliente" = p."idCliente_id"
        JOIN "Pedido_ProductoMenu" pp ON pp."idPedido_id" = p."idPedido"
        JOIN "ProductoMenu" pl ON pl."idProductoMenu" = pp."idProductoMenu_id"
        WHERE p."idPedido" IN (SELECT pp."idPedido_id" FROM "Pedido_ProductoMenu" pp 
                        WHERE pp."estado" IN ('Registrado', 'Listo', 'Servido')
                        GROUP BY pp."idPedido_id"
                        )
        GROUP BY p."idPedido", p."fecha", p."metodoPago", c."nombre"
        ORDER BY p."fecha" ASC;
    """)

    # 2. Obtener el detalle de platillos para los pedidos
    # Solo necesitamos los platillos que pertenecen a los pedidos en cola
    pedidos_ids = [p.idPedido for p in cola_pedidos]
    ProductoMenu_query = Pedido_ProductoMenu.objects.filter(idPedido__in=pedidos_ids).select_related('idProductoMenu').order_by('idPedido_id')
    
    # Pre-procesar platillos en un diccionario para acceso rápido en la plantilla
    ProductoMenu_por_pedido = {}
    for pp in ProductoMenu_query:
        # Estructura el objeto con la información necesaria
        item_info = {
            'IdPedido_Platillo': pp.pk,
            'IdPedido': pp.idPedido_id,
            'Nombre': pp.idProductoMenu.nombre,
            'Estado': pp.estado,
            'Cantidad': pp.cantidad,
        }
        if pp.idPedido_id not in ProductoMenu_por_pedido:
            ProductoMenu_por_pedido[pp.idPedido_id] = []
        ProductoMenu_por_pedido[pp.idPedido_id].append(item_info)

    # 3. Determinar el estado para la activación de botones (Facturar/Eliminar)
    estado_botones = {}
    for pedido in cola_pedidos:
        pedido_id = pedido.idPedido
        items = ProductoMenu_por_pedido.get(pedido_id, [])
        
        # Verificar estado para el botón 'Facturar'
        # Facturable: Todos los platillos en el pedido deben estar en estado 'Servido'
        puede_facturar = (len(items) > 0) and all(item['Estado'] == 'Servido' for item in items)
        
        # Verificar estado para el botón 'Eliminar'
        # Eliminable: Todos los platillos en el pedido deben estar en estado 'Registrado'
        puede_eliminar = (len(items) > 0) and all(item['Estado'] == 'Registrado' for item in items)
        
        estado_botones[pedido_id] = {
            'puede_facturar': puede_facturar,
            'puede_eliminar': puede_eliminar,
        }

    context = {
        'cola_pedidos': cola_pedidos,
        # Pasamos el diccionario pre-procesado a la plantilla
        'platillos_por_pedido': ProductoMenu_por_pedido, 
        'estado_botones': estado_botones, # Nuevo contexto para los botones
        'rol_empleado': request.user.rol,
        'nombre_mesero': request.user.nombre,
        'apellido_mesero': request.user.apellido,
        'metodos': ['Efectivo', 'Tarjeta', 'Transferencia']
    }
    return render(request, 'He_Sai_Mali/pedidos.html', context)

@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_registrarpedido(request, pedido_id=None):
    """
    Permite registrar un nuevo pedido o agregar platillos a un pedido existente (si se pasa pedido_id).
    
    LÓGICA DE MESA IMPLEMENTADA: Filtra mesas disponibles, asigna la mesa al crear el pedido 
    y la marca como OCUPADA.
    """
    menu_ProductoMenu = list(ProductoMenu.objects.raw("""SELECT * FROM "ProductoMenu" WHERE "disponible" = 'true'"""))
    
    pedido_existente = None
    if pedido_id:
        sql_pedido_existente = """
            SELECT p."idPedido", p."idCliente_id", p."idMesa_id", p."montoTotal", p."fecha", c."nombre" AS "cliente_nombre", c."telefono" AS "cliente_telefono"
            FROM "Pedido" p
            JOIN "Cliente" c ON c."idCliente" = p."idCliente_id"
            WHERE p."idPedido" = %s;
        """
        pedido_raw = list(Pedido.objects.raw(sql_pedido_existente, [pedido_id]))

        if pedido_raw:
            pedido_data = pedido_raw[0]

            class PedidoData:
                idPedido = pedido_data.idPedido
                montoTotal = pedido_data.montoTotal
                # Necesitamos obtener el objeto Mesa real para verificar su estado, si existe
                idMesa = Mesa.objects.filter(idMesa=pedido_data.idMesa_id).first() if pedido_data.idMesa_id else None 
                class idCliente:
                    nombre = pedido_data.cliente_nombre
                    telefono = pedido_data.cliente_telefono
                
                idCliente_id = pedido_data.idCliente_id
                idMesa_id = pedido_data.idMesa_id
            
            pedido_existente = PedidoData()


    # ------------------ LOGICA POST ------------------
    if request.method == 'POST':
        nombre_cliente = request.POST.get('nombre_cliente')
        telefono_cliente =  request.POST.get('telefono_cliente')
        correo_cliente = request.POST.get('correo_cliente')

        tipo_cliente = request.POST.get('tipo_cliente') # 'persona' o 'empresa'
        identificacion_cliente = request.POST.get('identificacion_cliente')

        
        id_mesa_seleccionada = request.POST.get('mesa') 
        
        if not nombre_cliente:
            messages.error(request, 'El nombre del cliente es obligatorio.')
            return redirect('registrarpedido')
            
        id_pedido_a_usar = None
        cliente_a_usar_id = None

        if telefono_cliente == "":
            telefono_cliente = None
        
        total_a_sumar = 0
        items_registrados = 0
        
        try:
            with transaction.atomic(): # Inicia una transacción atómica

                mesa_asignada_obj = None # Inicializar para usar fuera de los bloques

                if pedido_existente:
                    # Opción 1: Agregar a pedido existente
                    id_pedido_a_usar = pedido_existente.idPedido
                    # La mesa y cliente se mantienen del pedido existente
                    mesa_asignada_obj = pedido_existente.idMesa
                    
                else:
                    # Opción 2: Crear nuevo Cliente y Pedido (Encabezado)
                    
                    # A. Obtener/Crear Cliente
                    with connection.cursor() as cursor:
                        # 1. Buscar cliente por Nombre
                        sql_select_cliente = """
                            SELECT "idCliente" FROM "Cliente" WHERE "nombre" = %s LIMIT 1;
                        """
                        cursor.execute(sql_select_cliente, [nombre_cliente])
                        cliente_existente = cursor.fetchone()
                        
                        if cliente_existente:
                            cliente_a_usar_id = cliente_existente[0]
                        else:
                            # 2. Si no existe, crear nuevo cliente
                            sql_insert_cliente = """
                                INSERT INTO "Cliente" ("nombre", "telefono", "correo","tipoCliente","identificacion")
                                VALUES (%s, %s, %s,%s,%s)
                                RETURNING "idCliente";
                            """
                            cursor.execute(sql_insert_cliente, [nombre_cliente, telefono_cliente, correo_cliente, tipo_cliente, identificacion_cliente])
                            cliente_a_usar_id = cursor.fetchone()[0]


                    # B. ASIGNAR MESA Y MARCAR COMO OCUPADA
                    mesa_id_para_sql = None

                    if id_mesa_seleccionada and id_mesa_seleccionada != 'ninguna':
                        # Se seleccionó una mesa, buscar el objeto por su ID
                        mesa_asignada_obj = get_object_or_404(Mesa, pk=id_mesa_seleccionada)
                        
                        # Marcar como ocupada
                        mesa_asignada_obj.ocupada = True
                        mesa_asignada_obj.save()
                        
                        mesa_id_para_sql = mesa_asignada_obj.idMesa
                        
                    # C. Crear nuevo Pedido (incluyendo IdMesa_id)
                    with connection.cursor() as cursor:
                        sql_insert_pedido = """
                            INSERT INTO "Pedido" ("idCliente_id", "idMesa_id", "montoTotal", "fecha", "metodoPago","estadoDePago")
                            VALUES (%s, %s, %s, NOW() AT TIME ZONE 'CST', %s, False)
                            RETURNING "idPedido";
                        """
                        
                        cursor.execute(sql_insert_pedido, [cliente_a_usar_id, mesa_id_para_sql, 0.00, 'Pendiente'])
                        id_pedido_a_usar = cursor.fetchone()[0]
                        
                        # D. Asignar el nuevo pedido al Mesero (USO DE CURSOR)
                        sql_insert_empleado_pedido = """
                            INSERT INTO "Empleado_Pedido" ("idEmpleado_id", "idPedido_id", "fechaAsignacion")
                            VALUES (%s, %s, NOW() AT TIME ZONE 'CST');
                        """
                        cursor.execute(sql_insert_empleado_pedido, [request.user.idEmpleado, id_pedido_a_usar])
                
                # 2. Procesar los ProductosMenu seleccionados (Detalle)
                for productoMenu in menu_ProductoMenu:
                    cantidad = request.POST.get(f'cantidad_{productoMenu.idProductoMenu}', 0)
                    try:
                        cantidad = int(cantidad)
                    except ValueError:
                        cantidad = 0

                    if cantidad > 0:
                        with connection.cursor() as cursor:
                            # 2.1. Insertar el detalle del ProductoMenu
                            sql_insert_ProductoMenu_pedido = """
                                INSERT INTO "Pedido_ProductoMenu" ("idPedido_id", "idProductoMenu_id", "cantidad", "estado")
                                VALUES (%s, %s, %s, 'Registrado');
                            """
                            cursor.execute(sql_insert_ProductoMenu_pedido, [id_pedido_a_usar, productoMenu.idProductoMenu, cantidad])
                            
                            # 2.2. Restar ingredientes del stock
                            sql_ingredientes = """
                                SELECT "idArticuloInventario_id", "cantidad_usada" 
                                FROM "ProductoMenu_ArticuloInventario" 
                                WHERE "idProductoMenu_id" = %s;
                            """
                            cursor.execute(sql_ingredientes, [productoMenu.idProductoMenu])
                            for id_ingrediente, cantidad_usada in cursor.fetchall():
                                cantidad_a_restar = cantidad_usada * cantidad
                                sql_update_stock = """
                                    UPDATE "ArticuloInventario"
                                    SET "stock" = "stock" - %s
                                    WHERE "idArticuloInventario" = %s;
                                """
                                cursor.execute(sql_update_stock, [cantidad_a_restar, id_ingrediente])

                            total_a_sumar += productoMenu.precio * cantidad
                            items_registrados += cantidad
                
                # 3. Lógica de validación de 0 items si es pedido nuevo
                if items_registrados == 0:
                    if not pedido_existente:
                        # Si es un pedido nuevo y no se seleccionó nada, eliminar el encabezado
                        with connection.cursor() as cursor:
                            sql_delete_pedido = """
                                DELETE FROM "Pedido" WHERE "idPedido" = %s;
                            """
                            cursor.execute(sql_delete_pedido, [id_pedido_a_usar])
                        
                        # LIBERAR MESA SI SE HABÍA ASIGNADO Y LUEGO SE CANCELÓ
                        if mesa_asignada_obj:
                            mesa_asignada_obj.ocupada = False
                            mesa_asignada_obj.save()
                        
                        messages.error(request, "Debe seleccionar al menos un platillo para registrar el pedido.")
                        # Retornar a la misma vista con el mensaje de error
                        return redirect('registrarpedido') 
                    else:
                        messages.info(request, "No se añadieron nuevos platillos al pedido existente.")
                
                # 4. Actualizar el MontoTotal del pedido (usando ORM y F expressions)
                if items_registrados > 0:
                    Pedido.objects.filter(idPedido=id_pedido_a_usar).update(montoTotal=F('montoTotal') + total_a_sumar)
                    messages.success(request, f"Pedido N°{id_pedido_a_usar} registrado/actualizado con éxito.")
                
                return redirect('pedidos')
            
        except Exception as e:
            messages.error(request, e)
            return redirect('registrarpedido')
    
    # ------------------ PETICIÓN GET (Contexto) ------------------
    mesas_disponibles = Mesa.objects.filter(ocupada=False).order_by('idMesa') 

    # Petición GET
    context = {
        'platillos': menu_ProductoMenu,
        # Si es un pedido existente (para agregar), pre-rellenar el nombre del cliente
        'nombre_cliente_previo': pedido_existente.idCliente.nombre if pedido_existente else '',
        'telefono_cliente_previo': pedido_existente.idCliente.telefono if pedido_existente else '',
        'pedido_existente': pedido_existente,
        'mesas_disponibles': mesas_disponibles,
        'rol_empleado': request.user.rol,
        'nombre_empleado': request.user.nombre,
        'apellido_empleado': request.user.apellido
    }
    return render(request, 'He_Sai_Mali/registrarpedido.html', context)


@never_cache
@user_passes_test(es_rol("Cocinero"), login_url='login')
def vista_cocinero(request):
    sql_ProductoMenu_en_cola = """
        SELECT 
            pp."idPedido_ProductoMenu", 
            pp."cantidad", 
            pp."idPedido_id",
            p."nombre" AS "nombre_platillo",
            pd."fecha",
            c."nombre" AS "nombre_cliente",
            pd."idMesa_id"
        FROM "Pedido_ProductoMenu" pp
        JOIN "ProductoMenu" p ON p."idProductoMenu" = pp."idProductoMenu_id"
        JOIN "Pedido" pd ON pd."idPedido" = pp."idPedido_id"
        JOIN "Cliente" c ON c."idCliente" = pd."idCliente_id"
        WHERE pp."estado" = 'Registrado'
        ORDER BY pd."fecha" ASC, pp."idProductoMenu_id" ASC;
    """
    
    ProductoMenu_en_cola_raw = list(Pedido_ProductoMenu.objects.raw(sql_ProductoMenu_en_cola))

    # El platillo_en_cola más antiguo es el primero después de ordenar
    id_mas_antiguo = ProductoMenu_en_cola_raw[0].idPedido_id if ProductoMenu_en_cola_raw else None

    # Agrupar los platillos por pedido para la presentación en la cocina
    pedidos_activos = {}
    for pp in ProductoMenu_en_cola_raw:
        pedido_id = pp.idPedido.idPedido
        mesa = pp.idPedido.idMesa
        numero_mesa = "Mesa: "+str(mesa.idMesa) if mesa else "Sin Mesa"

        if pedido_id not in pedidos_activos:
            pedidos_activos[pedido_id] = {
                'id': pedido_id,
                'cliente': pp.idPedido.idCliente.nombre,
                'mesa': numero_mesa,
                'hora': pp.idPedido.fecha,
                'es_mas_antiguo': pedido_id == id_mas_antiguo,
                'platillos': []
            }
        pedidos_activos[pedido_id]['platillos'].append({
            'id_pp': pp.idPedido_ProductoMenu,
            'nombre': pp.idProductoMenu.nombre,
            'cantidad': pp.cantidad,
        })
    
    # Convertir el diccionario a una lista de diccionarios (ya está ordenado por la consulta)
    pedidos_ordenados = list(pedidos_activos.values())

    context = {
        'pedidos_en_cola': pedidos_ordenados,
    }
    return render(request, 'He_Sai_Mali/cocina.html', context)

@require_POST
@user_passes_test(es_rol("Cocinero"))
@login_required
def platillo_listo(request, pedido_platillo_id):
    """
    Marca un platillo específico dentro de un pedido como 'Listo'.
    """
    try:
        # USO DE CURSOR PARA SELECT Y UPDATE
        with connection.cursor() as cursor:
            # 1. Verificar si existe y está en estado 'Registrado'
            sql_select = """
                SELECT p."idProductoMenu_id", p."idPedido_id" FROM "Pedido_ProductoMenu" p
                WHERE "idPedido_ProductoMenu" = %s AND "estado" = 'Registrado';
            """
            cursor.execute(sql_select, [pedido_platillo_id])
            result = cursor.fetchone()
            
            if not result:
                messages.error(request, "Error: El platillo no se encontró o su estado ya no es 'Registrado'.")
                return redirect('cocina')
            
            platillo_id = result[0]
            pedido_id = result[1]
            
            # Obtener el nombre del platillo para el mensaje
            sql_get_nombre = """
                SELECT "nombre" FROM "ProductoMenu" WHERE "idProductoMenu" = %s;
            """
            cursor.execute(sql_get_nombre, [platillo_id])
            nombre_platillo = cursor.fetchone()[0]

            # 2. Cambiar el estado del platillo
            sql_update = """
                UPDATE "Pedido_ProductoMenu"
                SET "estado" = 'Listo'
                WHERE "idPedido_ProductoMenu" = %s;
            """
            cursor.execute(sql_update, [pedido_platillo_id])

        messages.success(request, f"El platillo '{nombre_platillo}' para el Pedido N°{pedido_id} ha sido marcado como LISTO.")

    except Exception as e:
        messages.error(request, f"Error al marcar como listo: {e}")

    # Redirigir de vuelta a la cola de la cocina
    return redirect('cocina')

@never_cache
@user_passes_test(es_rol("Administrador"))
@login_required
def admin_ingredientes(request):
    """
    Vista para ver ingredientes y proveedores.
    """
    context = {
        'ingredientes': ArticuloInventario.objects.all().order_by('nombre'),
        'proveedores': Proveedor.objects.all().order_by('nombre'),
        'rol_empleado': request.user.rol # Para el menú de navegación
    }
    return render(request, 'He_Sai_Mali/admin_ingredientes.html', context)

@require_POST
@user_passes_test(es_rol("Administrador"), login_url='login')
@login_required
def agregar_ingrediente(request):
    nombre = request.POST.get('nombre', '').strip()
    stock_str = request.POST.get('stock', '0')
    unidad_de_medida = request.POST.get('unidad_de_medida', '').strip()
    tipoArticulo = request.POST.get('tipo_articulo', '').strip()
    ubicacion = request.POST.get('ubicacion', '').strip()

    if not all([nombre, unidad_de_medida]):
        messages.error(request, 'El nombre y la unidad de medida son obligatorios para un nuevo ingrediente.')
        return redirect('admin_ingredientes')
    
    try:
        stock = float(stock_str)
        if stock < 0:
            messages.error(request, 'El stock inicial no puede ser negativo.')
            return redirect('admin_ingredientes')
            
        ArticuloInventario.objects.create(
            nombre=nombre,
            stock=stock,
            unidad_de_medida=unidad_de_medida,
            tipoArticulo=tipoArticulo,
            ubicacion=ubicacion
        )
        messages.success(request, f'Ingrediente "{nombre}" agregado exitosamente con stock inicial de {stock} {unidad_de_medida}.')
    except ValueError:
        messages.error(request, 'El stock debe ser un número válido.')
    except Exception as e:
        messages.error(request, f'Error al guardar el ingrediente: El nombre o los datos son inválidos. {e}')
    
    return redirect('admin_ingredientes')

@require_POST
@user_passes_test(es_rol("Administrador"), login_url='login')
@login_required
def comprar_ingrediente(request):
    """
    Procesa la compra de un ingrediente, registra el ArticuloInventario_Proveedor 
    y actualiza el stock del ArticuloInventario.
    """
    # 1. Obtener y validar datos
    id_ingrediente = request.POST.get('id_ingrediente')
    id_proveedor = request.POST.get('id_proveedor_fk') # ID oculto del proveedor
    precio_compra_str = request.POST.get('precio_compra')
    cantidad_comprada_str = request.POST.get('cantidad_comprada')
    fecha_compra = request.POST.get('fecha_compra')

    if not all([id_ingrediente, id_proveedor, precio_compra_str, cantidad_comprada_str, fecha_compra]):
        messages.error(request, 'Todos los campos son obligatorios.')
        return redirect('admin_ingredientes')

    try:
        # Conversión de tipos
        id_ingrediente = int(id_ingrediente)
        id_proveedor = int(id_proveedor)
        precio_compra = float(precio_compra_str)
        cantidad_comprada = float(cantidad_comprada_str)
        
        if cantidad_comprada <= 0 or precio_compra <= 0:
            messages.error(request, 'La cantidad y el precio deben ser valores positivos.')
            return redirect('admin_ingredientes')

        with transaction.atomic():
            # 2. Registrar la compra en la tabla intermedia (ArticuloInventario_Proveedor)
            # Se usa una consulta SQL directa con connection.cursor() por si el ORM de Django
            # no maneja un modelo intermedio sin primary key por defecto o para asegurar 
            # la atomicidad y el orden.
            with connection.cursor() as cursor:
                sql_insert_compra = """
                    INSERT INTO "ArticuloInventario_Proveedor" 
                    ("idArticuloInventario_id", "idProveedor_id", "precioCompra", "cantidadCompra", "fechaCompra")
                    VALUES (%s, %s, %s, %s, %s);
                """
                cursor.execute(sql_insert_compra, [
                    id_ingrediente, 
                    id_proveedor, 
                    precio_compra, 
                    cantidad_comprada,
                    fecha_compra
                ])

            # 3. Actualizar el stock del ArticuloInventario
            ArticuloInventario.objects.filter(pk=id_ingrediente).update(
                stock=F('stock') + cantidad_comprada
            )

        messages.success(request, f'Compra registrada. Stock de {cantidad_comprada} agregado.')

    except (ValueError, TypeError):
        messages.error(request, 'Error: El ID, precio y la cantidad deben ser números válidos.')
    except Exception as e:
        # Esto captura errores de base de datos o si no existen los IDs
        messages.error(request, f'Error al procesar la compra: Verifique el ingrediente y proveedor. ({e})')

    return redirect('admin_ingredientes')

@login_required
@user_passes_test(es_rol("Administrador"), login_url='login')
@require_POST
def eliminar_ingrediente(request, ingrediente_id):
    """
    Vista para eliminar un ArticuloInventario (Ingrediente).
    """
    try:
        # 1. Obtener el ingrediente o lanzar 404 si no existe
        articulo = get_object_or_404(ArticuloInventario, idArticuloInventario=ingrediente_id)
        
        # 2. Intentar eliminar
        articulo_nombre = articulo.nombre
        articulo.delete()
        
        # 3. Mensaje de éxito
        messages.success(request, f'El ingrediente "{articulo_nombre}" ha sido eliminado correctamente.')

    except Exception as e:
        # 4. Mensaje de error (por si hay referencias a este ingrediente, p. ej., en ProductoMenu_ArticuloInventario)
        # Nota: El on_delete=models.PROTECT en ArticuloInventario_Proveedor o ProductoMenu_ArticuloInventario
        # podría causar una excepción ProtectedError.
        messages.error(request, f'Error al intentar eliminar el ingrediente: {e}.')

    # 5. Redirigir de vuelta a la lista de ingredientes
    return redirect('admin_ingredientes')

@never_cache
@user_passes_test(es_rol("Administrador"))
@login_required
def admin_platillos(request):
    """
    Vista para agregar nuevos platillos (solo Admin).
    """
    articulos_inventario = ArticuloInventario.objects.all().order_by('nombre')

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        precio = request.POST.get('precio', 0)
        tiempoPreparacion = request.POST.get('tiempoPreparacion', '').strip()
        categoria = request.POST.get('categoria', '').strip()

        articulos_ids = request.POST.getlist('idArticuloInventario[]')
        cantidades = request.POST.getlist('cantidad_usada[]')

        if not nombre or not precio or not tiempoPreparacion:
            messages.error(request, 'El nombre, precio, categoría y tiempo de preparacion son obligatorios.')
        elif not articulos_ids:
            messages.error(request, 'Debe seleccionar al menos un artículo de inventario.')
        else:
            try:
                precio = float(precio)
                
                with transaction.atomic():
                    # A. Crear el ProductoMenu
                    nuevo_platillo = ProductoMenu.objects.create(
                        nombre=nombre,
                        precio=precio,
                        tiempoPreparacion=tiempoPreparacion,
                        categoria=categoria # Guardar el campo de categoría
                    )
                    
                    # B. Asociar los ArticuloInventario y cantidades
                    for art_id_str, cantidad_str in zip(articulos_ids, cantidades):
                        # Convertir a tipos correctos y validar
                        art_id = int(art_id_str)
                        cantidad = float(cantidad_str)

                        if cantidad <= 0:
                            raise ValueError("La cantidad usada de un ingrediente debe ser mayor a cero.")

                        ArticuloInventario_obj = ArticuloInventario.objects.get(pk=art_id)
                        
                        ProductoMenu_ArticuloInventario.objects.create(
                            idProductoMenu=nuevo_platillo,
                            idArticuloInventario=ArticuloInventario_obj,
                            cantidad_usada=cantidad
                        )

                messages.success(request, f'Platillo "{nombre}" agregado exitosamente con sus ingredientes.')
            
            except ValueError as ve:
                messages.error(request, f'Error de validación: {ve}')
            except ArticuloInventario.DoesNotExist:
                messages.error(request, 'Error: Se intentó usar un Artículo de Inventario no existente.')
            except Exception as e:
                # Si el error es de unicidad (nombre ya existe)
                if 'unique' in str(e).lower() and 'nombre' in str(e):
                     messages.error(request, f'Error: Ya existe un platillo con el nombre "{nombre}".')
                else:
                    messages.error(request, f'Error al guardar el platillo: {e}')

        return redirect('admin_platillos')

    # --- Lógica GET y Contexto ---
    # La categoría ahora se obtiene de la base de datos
    context = {
        'platillos': ProductoMenu.objects.all().order_by('idProductoMenu'),
        'categorias': ProductoMenu.objects.values_list('categoria', flat=True).distinct(), # Obtener categorías existentes
        'articulos_inventario': articulos_inventario, # Pasar la lista de artículos para el selector
        'rol_empleado': request.user.rol,
        'nombre_empleado': request.user.nombre,
        'apellido_empleado': request.user.apellido,
    }
    return render(request, 'He_Sai_Mali/admin_platillos.html', context)

@never_cache
@user_passes_test(es_rol("Administrador"))
@login_required
def toggle_disponibilidad_platillo(request, platillo_id):
    """
    Alterna el estado 'disponible' de un platillo.
    """
    if request.method == 'POST':
        try:
            platillo = ProductoMenu.objects.get(pk=platillo_id)
            # Alternar el estado booleano
            platillo.disponible = not platillo.disponible
            platillo.save()
            
            estado = "Disponible" if platillo.disponible else "No Disponible"
            messages.success(request, f'Estado de "{platillo.nombre}" cambiado a: {estado}.')
        
        except ProductoMenu.DoesNotExist:
            messages.error(request, f'Error: Platillo con ID {platillo_id} no encontrado.')
        except Exception as e:
            messages.error(request, f'Error al cambiar disponibilidad: {e}')

    return redirect('admin_platillos')

@require_POST
@user_passes_test(es_rol("Administrador"), login_url='login')
@login_required
def eliminar_platillo(request, platillo_id):
    """
    Elimina un ProductoMenu (platillo) y sus ingredientes relacionados.
    Si el platillo tiene pedidos asociados, la eliminación es bloqueada por ProtectedError.
    """
    platillo = get_object_or_404(ProductoMenu, pk=platillo_id)
    nombre_platillo = platillo.nombre
    
    try:
        with transaction.atomic():
            # La eliminación también eliminará automáticamente los registros en 
            # ProductoMenu_ArticuloInventario debido a models.CASCADE.
            platillo.delete()
        
        messages.success(request, f'El platillo "{nombre_platillo}" ha sido eliminado exitosamente.')
    
    except ProtectedError as e:
        messages.error(request, f'{e},No se puede eliminar el platillo "{nombre_platillo}" porque tiene pedidos asociados. Debe eliminar los pedidos relacionados primero.')
    except Exception as e:
        messages.error(request, f'Ocurrió un error inesperado al intentar eliminar el platillo: {e}')

    return redirect('admin_platillos')

@never_cache
@user_passes_test(es_rol("Administrador"))
@login_required
def admin_proveedores(request):
    """
    Vista para agregar nuevos proveedores (solo Admin).
    """
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        
        if not nombre:
            messages.error(request, 'El nombre del proveedor es obligatorio.')
        else:
            try:
                Proveedor.objects.create(
                    nombre=nombre,
                    telefono=telefono or None,
                    direccion=direccion or None,
                )
                messages.success(request, f'Proveedor "{nombre}" agregado exitosamente.')
            except Exception as e:
                messages.error(request, f'Error al guardar el proveedor: {e}')
        
        return redirect('admin_proveedores')

    context = {
        'proveedores': Proveedor.objects.all().order_by('idProveedor')
    }
    return render(request, 'He_Sai_Mali/admin_proveedores.html', context)

@require_POST
@user_passes_test(es_rol("Administrador"), login_url='login')
@login_required
def eliminar_proveedor(request, proveedor_id):
    """
    Vista para eliminar un Proveedor.
    """
    try:
        # 1. Obtener el proveedor o lanzar 404 si no existe
        # Usamos pk para buscar por idProveedor
        proveedor = get_object_or_404(Proveedor, pk=proveedor_id)
        
        # 2. Intentar eliminar
        proveedor_nombre = proveedor.nombre
        proveedor.delete()
        
        # 3. Mensaje de éxito
        messages.success(request, f'El proveedor "{proveedor_nombre}" ha sido eliminado correctamente.')

    except Exception as e:
        # 4. Mensaje de error
        # El on_delete=models.PROTECT en ArticuloInventario_Proveedor causará una excepción 
        # si hay ingredientes asociados a este proveedor.
        messages.error(request, f'Error al intentar eliminar el proveedor: {e}. Asegúrate de que no haya ingredientes asociados a este proveedor.')

    # 5. Redirigir de vuelta a la lista de proveedores
    return redirect('admin_proveedores')

@never_cache
@user_passes_test(es_rol("Administrador"))
@login_required
def admin_mesas(request):
    
    # Contexto base para el renderizado
    context = {
        'mesas': Mesa.objects.all().order_by('idMesa'),
        'user': request.user,
        'mesa_seleccionada': None, # Usado para precargar el formulario de edición
    }
    
    if request.method == 'POST':
        # 1. Obtener datos del formulario
        id_mesa_str = request.POST.get('idMesa', '').strip()
        capacidad_str = request.POST.get('capacidad', '').strip()
        action = request.POST.get('action') # 'add', 'edit', 'delete'

        # 2. Validar y Convertir datos básicos
        try:
            ocupada = False
            id_mesa = int(id_mesa_str) if id_mesa_str.isdigit() and id_mesa_str else None
            capacidad = int(capacidad_str) if capacidad_str.isdigit() and capacidad_str else None
            
        except ValueError:
            messages.error(request, "Error de datos: El ID y la Capacidad deben ser números enteros válidos.")
            return redirect('admin_mesas')

        # --- Lógica de Agregar (action='add') ---
        if action == 'add':
            if not capacidad or capacidad <= 0:
                messages.error(request, "Debe especificar una capacidad válida para agregar una mesa.")
                return redirect('admin_mesas')
                
            try:
                Mesa.objects.create(
                    idMesa=id_mesa,
                    capacidad=capacidad,
                    ocupada=ocupada
                )
                messages.success(request, f"Mesa de capacidad {capacidad} agregada exitosamente.")
            except Exception as e:
                messages.error(request, f"Error al agregar la mesa: {e}")

        # --- Lógica de Editar (action='edit') ---
        elif action == 'edit' and id_mesa is not None:
            if not capacidad or capacidad <= 0:
                messages.error(request, "Debe especificar una capacidad válida para editar la mesa.")
                return redirect('admin_mesas')
                
            try:
                mesa = get_object_or_404(Mesa, idMesa=id_mesa)
                mesa.capacidad = capacidad
                mesa.ocupada = ocupada
                mesa.save()
                messages.success(request, f"Mesa {id_mesa} actualizada exitosamente.")
            except Http404:
                messages.error(request, f"Error: No se encontró la Mesa con ID {id_mesa} para editar.")
            except Exception as e:
                messages.error(request, f"Error al editar la Mesa {id_mesa}: {e}")

        # --- Lógica de Eliminar (action='delete') ---
        elif action == 'delete' and id_mesa is not None:
            try:
                mesa = get_object_or_404(Mesa, idMesa=id_mesa)
                mesa.delete()
                messages.success(request, f"Mesa {id_mesa} eliminada permanentemente.")
            except Http404:
                messages.error(request, f"Error: No se encontró la Mesa con ID {id_mesa} para eliminar.")
            except Exception as e:
                messages.error(request, f"Error al eliminar la Mesa {id_mesa}: {e}")
        
        else:
            messages.error(request, "Acción no válida o falta el ID de Mesa para la operación solicitada.")

        return redirect('admin_mesas')

    # --- Lógica de Listado (GET) ---

    id_mesa_param = request.GET.get('id', '').strip()
    if id_mesa_param and id_mesa_param.isdigit():
        try:
            context['mesa_seleccionada'] = Mesa.objects.get(idMesa=int(id_mesa_param))
        except Mesa.DoesNotExist:
            messages.warning(request, f"La Mesa con ID {id_mesa_param} no existe.")
            
    return render(request, 'He_Sai_Mali/mesas.html', context)

# --- VISTA DE DASHBOARD PARA ADMINISTRADOR (NUEVA) ---
@login_required
@user_passes_test(es_rol("Administrador"))
def admin_dashboard(request):
    # 1. Lógica de Filtrado por Fecha
    period = request.GET.get('period', 'month') # 'day', 'week', 'month', 'year'
    today = timezone.now().date()
    start_date = None

    if period == 'day':
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, today.day))
        period_display = "Hoy"
    elif period == 'week':
        # Inicio de la semana (Lunes)
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, today.day)) - timedelta(days=today.weekday())
        period_display = "Esta Semana"
    elif period == 'month':
        # Inicio del mes
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, 1))
        period_display = "Este Mes"
    elif period == 'year':
        # Inicio del año
        start_date = timezone.make_aware(timezone.datetime(today.year, 1, 1))
        period_display = "Este Año"
    else: # Por defecto: Mes
        start_date = timezone.make_aware(timezone.datetime(today.year, today.month, 1))
        period = 'month'
        period_display = "Este Mes"
    
    # Filtro de fecha y estado 'Facturado' (asumiendo que solo pedidos facturados son ventas)
    date_filter = {'fecha__gte': start_date, 'estadoDePago': True}
    
    # 2. Ventas Realizadas (Total Sales)
    # Total de ventas en el periodo
    total_sales_agg = Pedido.objects.filter(**date_filter).aggregate(total=Sum('montoTotal'))
    total_sales = total_sales_agg['total'] if total_sales_agg['total'] else 0.00
    
    # 3. Productos del Menú más Populares (Top 5)
    # Cuenta la cantidad total de cada producto vendido en el periodo
    top_products_query = Pedido_ProductoMenu.objects.filter(
        idPedido__in=Pedido.objects.filter(**date_filter).values_list('idPedido', flat=True)
    ).values(
        nombre=F('idProductoMenu__nombre')
    ).annotate(
        total_quantity=Sum('cantidad')
    ).order_by('-total_quantity')[:5]

    top_products_labels = [p['nombre'] for p in top_products_query]
    # Se convierte a lista de números (float) para ser usado en Chart.js
    top_products_data = [float(p['total_quantity']) for p in top_products_query]
    
    # 4. Mesas más Utilizadas (Top Tables)
    # Cuenta cuántos pedidos facturados se hicieron en cada mesa
    top_tables_query = Pedido.objects.filter(**date_filter).values(
    'idMesa' # Agrupamos por idMesa, la clave en el resultado es 'idMesa'
    ).annotate(
        total_orders=Count('idMesa')
    ).order_by('-total_orders')

    # Accedemos a 'idMesa'
    top_tables_labels = [f"Mesa {t['idMesa']}" for t in top_tables_query] 
    top_tables_data = [t['total_orders'] for t in top_tables_query]

    # Conteo de pedidos totales en el periodo
    total_orders = Pedido.objects.filter(**date_filter).count()

    # Conteo de mesas activas (Mesas existentes)
    total_mesas = Mesa.objects.count()

    context = {
        'total_sales': total_sales,
        'total_orders': total_orders,
        'total_mesas': total_mesas,
        'period': period,
        'period_display': period_display,
        'top_products_labels': json.dumps(top_products_labels),
        'top_products_data': json.dumps(top_products_data),
        'top_tables_labels': json.dumps(top_tables_labels),
        'top_tables_data': json.dumps(top_tables_data),
    }
    return render(request, 'He_Sai_Mali/dashboard.html', context)

def vista_qr_mesas(request, mesa_id):
    mesa = get_object_or_404(Mesa, idMesa=mesa_id)
    
    # 2. Construir la URL que contendrá el QR (la del temporizador)
    # Se asume que 'temporizador_mesas' es el name de la ruta de destino del QR.
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

# =========================================================
# Temporizador para una mesa específica
# =========================================================
def temporizador_mesa(request, mesa_id):
    """
    Calcula el tiempo restante para el último pedido de la mesa 
    y renderiza la vista del temporizador.
    """
    # Se verifica que la mesa exista
    mesa = get_object_or_404(Mesa, idMesa=mesa_id)
    
    # 1. Obtener el pedido más reciente para esta mesa
    # Filtra por la mesa y ordena por `tiempo_inicio` de forma descendente.
    latest_pedido = Pedido.objects.filter(
        idMesa=mesa,
    ).order_by('idPedido').first()

    remaining_seconds = 0
    
    if latest_pedido:
        # Duración total: Usamos la constante de 3 minutos (180s)
        # A futuro, podrías usar: latest_pedido.tiempo
        total_duration_seconds = 180
        
        start_time = latest_pedido.fecha

        # Hora en que el temporizador debería terminar
        end_time = start_time + timedelta(seconds=total_duration_seconds)

        # Cálculo del tiempo restante
        time_difference = end_time - timezone.localtime(timezone.now()) + timedelta(hours=6)

        # Aseguramos que el tiempo restante no sea negativo
        remaining_seconds = max(0, int(time_difference.total_seconds()))
    
    context = {
        'mesa_id': mesa_id,
        'remaining_seconds': remaining_seconds, # El tiempo restante en segundos
        'has_active_pedido': remaining_seconds > 0,
        'tiempo_total_segundos': 180 # Útil para mostrar la duración total
    }
    
    return render(request, 'He_Sai_Mali/temporizador.html', context)

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
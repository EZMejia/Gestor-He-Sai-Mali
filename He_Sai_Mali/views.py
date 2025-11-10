from django.db import connection, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test

from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db.models import F

from .models import *

import re

from .decorators import es_rol

# Create your views here.
def main(request):
    return render(request, 'He_Sai_Mali/main.html')

def origen(request):
    return render(request, 'He_Sai_Mali/origen.html')

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
            sql_select_correo = """SELECT COUNT(*) FROM "Empleado" WHERE "Correo" = %s"""
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
                    sql_select_usuario = """SELECT COUNT(*) FROM "Empleado" WHERE "Usuario" = %s"""
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
                INSERT INTO "Empleado" ("Nombre", "Apellido", "Telefono", "Correo", "Cedula", "Rol", "Usuario", "password", "is_active", "is_staff","is_superuser", "date_joined")
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, FALSE, NOW());
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
        rol = (request.user.Rol or '').strip().lower()
        if rol == "administrador":
            return redirect('pedidos')
        elif rol == "mesero":
            return redirect('pedidos')
        elif rol == "cocinero":
            return redirect('cocina')
        else:
            # Por defecto, si el rol no está claro o no es ninguno de los anteriores
            return redirect('pedidos')
    
    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        contrasena = request.POST.get('contrasena')

        if not usuario or not contrasena:
            messages.error(request, 'Usuario y contraseña son obligatorios.')
        else:
            user = authenticate(request, username=usuario, password=contrasena)
            if user is not None:
                login(request, user)
                rol = (user.Rol or '').strip().lower()
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
    """Cambia el estado de un Platillo dentro de un Pedido (Pedido_Platillo)."""
    # Usamos get_object_or_404 para manejar el caso de ID no encontrado
    pedido_platillo = get_object_or_404(Pedido_Platillo, pk=pedido_platillo_id)
    
    current_state = pedido_platillo.Estado
    next_state = None
    
    # Lógica de transición de estado
    if current_state == 'Registrado':
        next_state = 'Listo'
    elif current_state == 'Listo':
        next_state = 'Servido'
    elif current_state == 'Servido':
        next_state = 'Facturado' # El mesero puede forzarlo a Facturado, aunque la Facturación masiva es con el botón

    if next_state:
        pedido_platillo.Estado = next_state
        pedido_platillo.save()
        messages.success(request, f"Estado de {pedido_platillo.IdPlatillo.Nombre} cambiado a '{next_state}'.")
    else:
        messages.info(request, f"El estado de {pedido_platillo.IdPlatillo.Nombre} es '{current_state}', no se puede cambiar.")

    # Redirigir a la vista principal de pedidos
    return redirect('pedidos')

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def facturar_pedido(request, pedido_id):
    """
    Cambia el estado de *todos* los platillos de un pedido a 'Facturado'
    solo si todos están en estado 'Servido'.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    
    # 1. Verificar si todos los platillos están en 'Servido'
    items_facturables = pedido.items.exclude(Estado='Facturado').count()
    items_servidos = pedido.items.filter(Estado='Servido').count()
    
    # Solo se factura si todos los ítems restantes (no facturados) están en 'Servido'
    if items_facturables > 0 and items_facturables == items_servidos:
        with transaction.atomic():
            # 2. Actualizar el estado de todos los Pedido_Platillo a 'Facturado'
            pedido.items.all().update(Estado='Facturado')
            
            # Opcional: Podrías añadir lógica para registrar el método de pago 
            # en el modelo Pedido aquí si fuera necesario.
            
            messages.success(request, f"Pedido N°{pedido.IdPedido} facturado exitosamente. Todos los platillos están en estado 'Facturado'.")
    elif items_facturables == 0:
        messages.info(request, f"Pedido N°{pedido.IdPedido} ya está completamente facturado.")
    else:
        # 3. Si no todos están en 'Servido', no se factura
        messages.warning(request, f"No se puede facturar el Pedido N°{pedido.IdPedido}. No todos los platillos están en estado 'Servido'.")

    return redirect('pedidos')

@require_POST
@user_passes_test(es_rol("Mesero"), login_url='login')
def eliminar_pedido(request, pedido_id):
    """
    Elimina un Pedido si *todos* sus platillos están aún en estado 'Registrado'.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    # 1. Verificar si todos los platillos están en 'Registrado'
    # Contamos cuántos NO están en 'Registrado'
    items_no_registrados = pedido.items.exclude(Estado='Registrado').count()
    
    if items_no_registrados == 0:
        # Si la cuenta es 0, todos están en 'Registrado'
        with transaction.atomic():
            # Django con on_delete=models.CASCADE se encarga de Pedido_Platillo y Empleado_Pedido
            pedido.delete() 
            messages.success(request, f"Pedido N°{pedido_id} eliminado exitosamente.")
    else:
        messages.error(request, f"No se puede eliminar el Pedido N°{pedido_id}. Algunos platillos ya han cambiado de estado (Listo/Servido/Facturado).")

    return redirect('pedidos')

# --- Fin de Vistas de Acción ---

@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_mesero(request):
    """Muestra la cola de pedidos activos y obtiene el estado de facturación/registro para los botones."""
    
    # 1. Obtener los pedidos que tienen al menos un platillo no facturado
    cola_pedidos = Pedido.objects.raw("""
        SELECT p."IdPedido", p."Fecha", p."MontoTotal", p."MetodoPago", c."Nombre"
        FROM "Pedido" p
        JOIN "Cliente" c ON c."IdCliente" = p."IdCliente_id"
        WHERE p."IdPedido" IN (SELECT pp."IdPedido_id" FROM "Pedido_Platillo" pp 
                        WHERE pp."Estado" IN ('Registrado', 'Listo', 'Servido')
                        GROUP BY pp."IdPedido_id"
                        )
        ORDER BY p."Fecha" ASC;
    """)

    # 2. Obtener el detalle de platillos para los pedidos
    # Solo necesitamos los platillos que pertenecen a los pedidos en cola
    pedidos_ids = [p.IdPedido for p in cola_pedidos]
    platillos_query = Pedido_Platillo.objects.filter(IdPedido__in=pedidos_ids).select_related('IdPlatillo').order_by('IdPedido_id')
    
    # Pre-procesar platillos en un diccionario para acceso rápido en la plantilla
    platillos_por_pedido = {}
    for pp in platillos_query:
        # Estructura el objeto con la información necesaria
        item_info = {
            'IdPedido_Platillo': pp.pk,
            'IdPedido': pp.IdPedido_id,
            'Nombre': pp.IdPlatillo.Nombre,
            'Estado': pp.Estado,
            'Cantidad': pp.Cantidad,
        }
        if pp.IdPedido_id not in platillos_por_pedido:
            platillos_por_pedido[pp.IdPedido_id] = []
        platillos_por_pedido[pp.IdPedido_id].append(item_info)

    # 3. Determinar el estado para la activación de botones (Facturar/Eliminar)
    estado_botones = {}
    for pedido in cola_pedidos:
        pedido_id = pedido.IdPedido
        items = platillos_por_pedido.get(pedido_id, [])
        
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
        'platillos_por_pedido': platillos_por_pedido, 
        'estado_botones': estado_botones, # Nuevo contexto para los botones
        'rol_empleado': request.user.Rol,
        'nombre_mesero': request.user.Nombre,
        'apellido_mesero': request.user.Apellido
    }
    return render(request, 'He_Sai_Mali/pedidos.html', context)

@never_cache
@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_registrarpedido(request, pedido_id=None):
    """
    Permite registrar un nuevo pedido o agregar platillos a un pedido existente (si se pasa pedido_id).
    """
    menu_platillos = list(Platillo.objects.raw("""SELECT * FROM "Platillo" """))
    
    pedido_existente = None
    if pedido_id:
        pedido_existente = get_object_or_404(Pedido.objects.select_related('IdCliente', 'IdMesa'), pk=pedido_id)

    if request.method == 'POST':
        nombre_cliente = request.POST.get('nombre_cliente')
        telefono_cliente =  request.POST.get('telefono_cliente')
        
        if not nombre_cliente:
            context = {
                'error_message': 'El nombre del cliente es obligatorio.',
                'platillos': menu_platillos,
                'nombre_cliente_previo': nombre_cliente,
                'pedido_existente': pedido_existente,
                'telefono_cliente_previo': telefono_cliente,
            }
            return render(request, 'He_Sai_Mali/registrarpedido.html', context)

        id_pedido_a_usar = None
        cliente_a_usar = None
        mesa_a_usar = None
        total_a_sumar = 0
        items_registrados = 0
        
        try:
            with transaction.atomic(): # Inicia una transacción atómica

                if pedido_existente:
                    # Opción 1: Agregar a pedido existente
                    id_pedido_a_usar = pedido_existente.IdPedido
                    cliente_a_usar = pedido_existente.IdCliente
                    mesa_a_usar = pedido_existente.IdMesa
                else:
                    # Opción 2: Crear nuevo Cliente y Pedido (Encabezado)
                    
                    # A. Obtener/Crear Cliente
                    # Se usa get_or_create para evitar duplicados si el nombre es el único identificador
                    cliente_a_usar, created = Cliente.objects.get_or_create(
                        Nombre=nombre_cliente,
                        Telefono=telefono_cliente,
                        # Puedes añadir más campos para la búsqueda si tienes más datos (ej: teléfono, correo)
                        defaults={'Nombre': nombre_cliente} 
                    )

                    # B. Asignar Mesa (Lógica simple: buscar la primera no ocupada)
                    """try:
                        mesa_a_usar = Mesa.objects.filter(Ocupada=False).first()
                        if not mesa_a_usar:
                            # Si no hay mesas libres, se puede manejar como un error o un pedido para llevar
                            raise Exception("No hay mesas libres disponibles.") 
                        
                        mesa_a_usar.Ocupada = True
                        mesa_a_usar.save()
                    except Exception as e:
                        messages.error(request, f"Error al asignar mesa: {e}. El pedido no se registrará.")
                        return redirect('pedidos')"""


                    # C. Crear nuevo Pedido (usando ORM)
                    nuevo_pedido = Pedido.objects.create(
                        IdCliente=cliente_a_usar,
                        IdMesa=mesa_a_usar,
                        MontoTotal=0.00,
                        Fecha=timezone.now()
                    )
                    id_pedido_a_usar = nuevo_pedido.IdPedido
                    
                    # D. Asignar el nuevo pedido al Mesero (usando ORM)
                    Empleado_Pedido.objects.create(
                        IdEmpleado_id=request.user.IdEmpleado, # Se asume que request.user es una instancia de Empleado
                        IdPedido=nuevo_pedido,
                        FechaAsignacion=timezone.now()
                    )
                
                # 2. Procesar los Platillos seleccionados (Detalle)
                for platillo in menu_platillos:
                    cantidad_key = f'cantidad_{platillo.IdPlatillo}'
                    cantidad_str = request.POST.get(cantidad_key, '0')
                    
                    try:
                        cantidad = int(cantidad_str)
                    except ValueError:
                        cantidad = 0

                    if cantidad > 0:
                        # Insertar en Pedido_Platillo (usando ORM)
                        Pedido_Platillo.objects.create(
                            IdPedido_id=id_pedido_a_usar,
                            IdPlatillo=platillo,
                            Cantidad=cantidad,
                            Estado='Registrado'
                        )

                        total_a_sumar += platillo.Precio * cantidad
                        items_registrados += 1
                
                # 3. Lógica de validación y actualización del total
                if items_registrados == 0:
                    if not pedido_existente:
                        # Si es un pedido nuevo y no se seleccionó nada, eliminar el encabezado y liberar la mesa
                        Pedido.objects.filter(IdPedido=id_pedido_a_usar).delete()
                        if mesa_a_usar:
                            mesa_a_usar.Ocupada = False
                            mesa_a_usar.save()
                        
                        context = {
                            'error_message': 'Debe seleccionar al menos un platillo.',
                            'platillos': menu_platillos,
                            'nombre_cliente_previo': nombre_cliente, # Para repoblar el campo
                            'telefono_cliente_previo': telefono_cliente,
                        }
                        return render(request, 'He_Sai_Mali/registrarpedido.html', context)
                    else:
                        # Si es un pedido existente y no se seleccionó nada que agregar
                        messages.info(request, "No se agregaron nuevos platillos al pedido.")
                        return redirect('pedidos')


                # 4. Actualizar el MontoTotal del pedido (usando ORM y F expressions)
                if total_a_sumar > 0:
                    Pedido.objects.filter(IdPedido=id_pedido_a_usar).update(
                        MontoTotal=F('MontoTotal') + total_a_sumar
                    )
                
                messages.success(request, f"Pedido N°{id_pedido_a_usar} registrado/actualizado con éxito.")
                return redirect('pedidos')
            
        except Exception as e:
            messages.error(request, f"Ocurrió un error al procesar el pedido: {e}")
            # Si algo falla en la transacción, se hace un rollback automáticamente

            # Si es un nuevo pedido que falló después de crear la mesa, intenta liberarla
            if not pedido_existente and 'mesa_a_usar' in locals() and mesa_a_usar:
                Mesa.objects.filter(IdMesa=mesa_a_usar.IdMesa).update(Ocupada=False)

            context = {
                'error_message': f'Error en el registro del pedido: {e}',
                'platillos': menu_platillos,
                'nombre_cliente_previo': nombre_cliente,
                'telefono_cliente_previo': telefono_cliente,
                'pedido_existente': pedido_existente,
            }
            return render(request, 'He_Sai_Mali/registrarpedido.html', context)
    
    # Petición GET
    context = {
        'platillos': menu_platillos,
        # Si es un pedido existente (para agregar), pre-rellenar el nombre del cliente
        'nombre_cliente_previo': pedido_existente.IdCliente.Nombre if pedido_existente else '',
        'telefono_cliente_previo': pedido_existente.IdCliente.Telefono if pedido_existente else '',
        'pedido_existente': pedido_existente
    }
    return render(request, 'He_Sai_Mali/registrarpedido.html', context)


@never_cache
@user_passes_test(es_rol("Cocinero"), login_url='login')
def vista_cocinero(request):
    return render(request, 'He_Sai_Mali/cocina.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
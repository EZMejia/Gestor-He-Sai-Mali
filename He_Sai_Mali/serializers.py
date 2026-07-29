import re
from rest_framework import serializers
from django.db import transaction
from django.core.validators import RegexValidator
from rest_framework.validators import UniqueValidator
from .models import *

# Listar los empleados
class EmpleadoListSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Empleado
        fields = ['idEmpleado', 'nombre', 'apellido', 'nombre_completo', 'usuario', 'rol', 'telefono', 'correo', 'cedula', 'is_active']

    def get_nombre_completo(self, obj):
        return f"{obj.nombre} {obj.apellido}"
    
# Reglas para editar empleado
class EditarEmpleadoSerializer(serializers.ModelSerializer):
    nueva_password = serializers.CharField(write_only=True, required=False, allow_blank=True, style={'input_type': 'password'})
    confirmar_password = serializers.CharField(write_only=True, required=False, allow_blank=True, style={'input_type': 'password'})
    
    nombre = serializers.CharField(validators=[RegexValidator(r'^[a-zA-Z\u00C0-\u017F\sñÑ]+$', 'El nombre solo puede contener letras y espacios.')])
    apellido = serializers.CharField(validators=[RegexValidator(r'^[a-zA-Z\u00C0-\u017F\sñÑ]+$', 'El apellido solo puede contener letras y espacios.')])
    telefono = serializers.CharField(validators=[RegexValidator(r'^\d{8}$', 'El teléfono debe ser de 8 dígitos numéricos.')])
    cedula = serializers.CharField(validators=[RegexValidator(r'^\d{3}-\d{6}-\d{4}[A-Z]$', 'El formato de Cédula debe ser 000-000000-0000X.')])

    class Meta:
        model = Empleado
        fields = ['nombre', 'apellido', 'telefono', 'correo', 'cedula', 'rol', 'nueva_password', 'confirmar_password']

    def validate(self, data):
        instance = self.instance # El empleado que estamos editando
        
        # 1. Validaciones de Unicidad Manuales (excluyendo la instancia actual)
        correo = data.get('correo')
        telefono = data.get('telefono')
        cedula = data.get('cedula')

        if correo and Empleado.objects.filter(correo=correo).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({"correo": f"Ya existe un empleado con el correo '{correo}'."})
        if telefono and Empleado.objects.filter(telefono=telefono).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({"telefono": f"Ya existe un empleado con el teléfono '{telefono}'."})
        if cedula and Empleado.objects.filter(cedula=cedula).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({"cedula": f"Ya existe un empleado con la cédula '{cedula}'."})

        # 2. Validar contraseñas si se envió 'nueva_password'
        nueva_pass = data.get('nueva_password')
        confirmar_pass = data.get('confirmar_password')

        if nueva_pass or confirmar_pass:
            if nueva_pass != confirmar_pass:
                raise serializers.ValidationError({"nueva_password": "Las contraseñas no coinciden."})
            
            # Replicar criterios de contraseña fuerte
            password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]{8,}$'
            if not re.match(password_regex, nueva_pass):
                raise serializers.ValidationError({
                    "nueva_password": "La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número."
                })

        return data

    def update(self, instance, validated_data):
        # Extraer contraseñas para procesarlas por separado
        nueva_pass = validated_data.pop('nueva_password', None)
        validated_data.pop('confirmar_password', None)

        # Actualizar campos estándar
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Encriptar y asignar contraseña si se incluyó
        if nueva_pass:
            instance.set_password(nueva_pass)

        instance.save()
        return instance

# Reglas para registrar nuevo empleado
class RegistroEmpleadoSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(
        validators=[RegexValidator(r'^[a-zA-Z\u00C0-\u017F\sñÑ]+$', 'El nombre solo puede contener letras y espacios.')]
    )
    apellido = serializers.CharField(
        validators=[RegexValidator(r'^[a-zA-Z\u00C0-\u017F\sñÑ]+$', 'El apellido solo puede contener letras y espacios.')]
    )
    
    correo = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=Empleado.objects.all(),
                message='Este correo electrónico ya está registrado por otro empleado.'
            )
        ]
    )
    
    telefono = serializers.CharField(
        validators=[
            RegexValidator(r'^\d{8}$', 'El teléfono debe ser de 8 dígitos numéricos.'),
            UniqueValidator(
                queryset=Empleado.objects.all(),
                message='Este número de teléfono ya está registrado por otro empleado.'
            )
        ]
    )
    
    cedula = serializers.CharField(
        validators=[
            RegexValidator(r'^\d{3}-\d{6}-\d{4}[A-Z]$', 'El formato de Cédula debe ser 000-000000-0000X.'),
            UniqueValidator(
                queryset=Empleado.objects.all(),
                message='Esta cédula ya está registrada por otro empleado.'
            )
        ]
    )

    rol = serializers.ChoiceField(choices=[('Administrador', 'Administrador'), ('Mesero', 'Mesero'), ('Cocinero', 'Cocinero'),])

    # NUEVO: Declaramos explícitamente el sucursal_id para que el serializador sepa qué hacer con él
    sucursal_id = serializers.IntegerField(required=False, allow_null=True)

    contrasena1 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    contrasena2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = Empleado
        # NUEVO: Añadimos 'sucursal_id' al final de la lista de fields
        fields = ['nombre', 'apellido', 'telefono', 'correo', 'cedula', 'rol', 'contrasena1', 'contrasena2', 'sucursal_id']

    def validate(self, data):
        # 1. Validar que las contraseñas coincidan
        if data['contrasena1'] != data['contrasena2']:
            raise serializers.ValidationError({"contrasena1": "Las contraseñas no coinciden."})

        # 2. Replicar el Regex de contraseña fuerte del frontend
        # Mínimo 8 caracteres, 1 mayúscula, 1 minúscula y 1 número
        password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]{8,}$'
        if not re.match(password_regex, data['contrasena1']):
            raise serializers.ValidationError({
                "contrasena1": "La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número."
            })

        return data

    def create(self, validated_data):
        # Retiramos las contraseñas del diccionario de datos validados
        validated_data.pop('contrasena2')
        contrasena = validated_data.pop('contrasena1')

        nombre = validated_data.get('nombre', '').strip()
        apellido = validated_data.get('apellido', '').strip()
        rol = validated_data.get('rol', '').strip()

        # Generar nombre de usuario
        def primeras_dos(palabra):
            return re.sub(r'[^a-zA-Z]', '', palabra).lower()[:2]
        
        base = primeras_dos(nombre) + primeras_dos(apellido) + rol.capitalize() + "HSM"
        usuario = base
        contador = 1

        # ORM de Django
        while Empleado.objects.filter(usuario=usuario).exists():
            usuario = f"{base}{contador}"
            contador += 1

        # Utilizamos el EmpleadoManager definido en models.py
        # Como agregaste sucursal_id a los fields, ya viene dentro de **validated_data.
        # Django se encarga de inyectarlo automáticamente en tu modelo.
        empleado = Empleado.objects.create_user(
            usuario=usuario,
            contrasena=contrasena,
            **validated_data
        )
        
        return empleado
    
# Reglas de Login
class LoginSerializer(serializers.Serializer):
    usuario = serializers.CharField(
        required=True,
        error_messages={'blank': 'El usuario no puede quedarse vacío.', 'required': 'El usuario es obligatorio.'}
    )
    contrasena = serializers.CharField(
        required=True,
        write_only=True,
        error_messages={'blank': 'La contraseña no puede quedarse vacía.', 'required': 'La contraseña es obligatoria.'}
    )

# Reglas de Proveedores
class ProveedorSerializer(serializers.ModelSerializer):
    # Forzar a que el teléfono sea obligatorio y cumpla con exactamente 8 números
    telefono = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[RegexValidator(r'^\d{8}$', 'El teléfono debe contener exactamente 8 dígitos numéricos.')]
    )

    direccion = serializers.CharField(
        required=True, 
        allow_blank=False,
        error_messages={
            'required': 'La dirección es obligatoria.',
            'blank': 'La dirección no puede quedarse vacía.',
            'null': 'La dirección no puede ser nula.'
        }
    )

    class Meta:
        model = Proveedor
        fields = ['idProveedor', 'nombre', 'telefono', 'direccion']
        extra_kwargs = {
            'nombre': {
                'error_messages': {
                    'required': 'El nombre del proveedor es obligatorio.',
                    'blank': 'El nombre no puede quedarse vacío.'
                }
            }
        }

    def validate_nombre(self, value):
        nombre_limpio = value.strip()
        instance = self.instance
        
        queryset = Proveedor.objects.filter(nombre__iexact=nombre_limpio)
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
            
        if queryset.exists():
            raise serializers.ValidationError(f"Ya existe un proveedor con el nombre '{nombre_limpio}'.")
        return nombre_limpio
    
# Reglas de Mesas
class MesaSerializer(serializers.ModelSerializer):
    # Forzar a que sean enteros en la validación de la API
    idMesa = serializers.IntegerField(min_value=1, error_messages={
        'min_value': 'El número de mesa debe ser mayor a cero.',
        'invalid': 'El número de mesa debe ser un número entero válido.'
    })
    capacidad = serializers.IntegerField(min_value=1, error_messages={
        'min_value': 'La capacidad debe ser mayor a cero.',
        'invalid': 'La capacidad debe ser un número entero válido.'
    })

    ocupada = serializers.BooleanField(read_only=True)

    class Meta:
        model = Mesa
        fields = ['idMesa', 'capacidad', 'ocupada']

    def validate_idMesa(self, value):
        # Validación de unicidad manual solo al CREAR (POST)
        if not self.instance and Mesa.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"Ya existe una mesa con el número '{value}'.")
        return value
    
# Reglas para articulo_inventario
class ArticuloInventarioSerializer(serializers.ModelSerializer):
    # Validaciones personalizadas con mensajes claros para campos obligatorios
    nombre = serializers.CharField(
        required=True,
        error_messages={
            'blank': 'El nombre del ingrediente es obligatorio.',
            'required': 'El campo nombre es mandatorio.'
        }
    )
    unidad_de_medida = serializers.CharField(
        required=True,
        error_messages={
            'blank': 'La unidad de medida es obligatoria.',
            'required': 'El campo unidad de medida es mandatorio.'
        }
    )
    # Cambiado a FloatField o DecimalField dependiendo de tu modelo, 
    # se mantiene FloatField pero validando el valor mínimo por seguridad.
    stock = serializers.FloatField(
        required=False, 
        min_value=0.0,
        error_messages={'min_value': 'El stock inicial no puede ser un número negativo.'}
    )
    
    tipoArticulo = serializers.CharField(required=True, error_messages={'blank': 'El tipo de artículo es requerido.'})

    class Meta:
        model = ArticuloInventario
        fields = ['idArticuloInventario', 'nombre', 'stock', 'unidad_de_medida', 'tipoArticulo', 'ubicacion']

    def validate_nombre(self, value):
        # Eliminar espacios innecesarios al inicio y al final
        nombre_limpio = value.strip()
        if not nombre_limpio:
            raise serializers.ValidationError("El nombre no puede consistir únicamente de espacios en blanco.")
            
        instance = self.instance
        queryset = ArticuloInventario.objects.filter(nombre__iexact=nombre_limpio)
        
        # Si estamos editando, excluimos el objeto actual de la búsqueda de duplicados
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
            
        if queryset.exists():
            raise serializers.ValidationError(f"Ya existe un artículo en el inventario con el nombre '{nombre_limpio}'.")
            
        return nombre_limpio


# Serializador de apoyo para validar los datos estructurados al comprar
class CompraIngredienteSerializer(serializers.Serializer):
    id_proveedor_fk = serializers.IntegerField(
        required=True,
        error_messages={'required': 'Debe seleccionar un proveedor válido.'}
    )
    precio_compra = serializers.FloatField(
        min_value=0.01, 
        error_messages={'min_value': 'El precio de compra debe ser un valor positivo mayor a cero.'}
    )
    cantidad_comprada = serializers.FloatField(
        min_value=0.01, 
        error_messages={'min_value': 'La cantidad comprada debe ser un valor positivo mayor a cero.'}
    )
    fecha_compra = serializers.DateField(
        required=True,
        error_messages={'invalid': 'Formato de fecha inválido. Utilice el formato AAAA-MM-DD.'}
    )


# Serializador de apoyo para registrar pérdidas o mermas
class MermaIngredienteSerializer(serializers.Serializer):
    cantidad_merma = serializers.FloatField(
        min_value=0.01, 
        error_messages={'min_value': 'La cantidad de pérdida o merma debe ser un valor positivo mayor a cero.'}
    )

# Serializador para la cantidad de ingreidentes en una receta
class IngredienteRecetaSerializer(serializers.ModelSerializer):
    # Permite recibir el id del artículo y leer dinámicamente sus datos básicos
    idArticuloInventario = serializers.PrimaryKeyRelatedField(
        queryset=ArticuloInventario.objects.all()
    )
    nombre = serializers.CharField(source='idArticuloInventario.nombre', read_only=True)
    unidad_de_medida = serializers.CharField(source='idArticuloInventario.unidad_de_medida', read_only=True)

    class Meta:
        model = ProductoMenu_ArticuloInventario
        fields = ['idArticuloInventario', 'nombre', 'unidad_de_medida', 'cantidad_usada']
        extra_kwargs = {
            'cantidad_usada': {
                'min_value': 0.01,
                'error_messages': {'min_value': 'La cantidad usada de un ingrediente debe ser mayor a cero.'}
            }
        }

# Serializador para los platillos
class ProductoMenuSerializer(serializers.ModelSerializer):
    # Relación inversa usando el manager relacional por defecto de Django[cite: 6]
    ingredientes = IngredienteRecetaSerializer(many=True, source='productomenu_articuloinventario_set')

    class Meta:
        model = ProductoMenu
        fields = ['idProductoMenu', 'nombre', 'categoria', 'precio', 'tiempoPreparacion', 'disponible', 'ingredientes']
        extra_kwargs = {
            'nombre': {
                'required': True,
                'allow_blank': False,
                'error_messages': {
                    'required': 'El campo nombre es obligatorio.',
                    'blank': 'El nombre no puede quedarse vacío.'
                }
            },
            'precio': {
                'required': True,
                'min_value': 0.0,
                'error_messages': {
                    'required': 'El precio del producto es obligatorio.',
                    'invalid': 'El precio debe ser un número válido.',
                    'min_value': 'El precio no puede ser un número negativo.'
                }
            },
            'categoria': {
                'required': True,
                'allow_blank': False,
                'error_messages': {
                    'required': 'La categoría es obligatoria para organizar el menú.',
                    'blank': 'La categoría no puede quedarse vacía.'
                }
            },
            'tiempoPreparacion': {
                'required': True,
                'min_value': 0,
                'error_messages': {
                    'required': 'El tiempo de preparación es obligatorio.',
                    'invalid': 'El tiempo de preparación debe ser un número entero.',
                    'min_value': 'El tiempo de preparación no puede ser negativo.'
                }
            }
        }

    def validate_ingredientes(self, value):
        if not value:
            raise serializers.ValidationError("Debe seleccionar al menos un artículo de inventario.")
        return value

    def create(self, validated_data):
        ingredientes_data = validated_data.pop('productomenu_articuloinventario_set', [])
        
        try:
            # Bloque transaccional idéntico a la lógica original[cite: 6]
            with transaction.atomic():
                nuevo_platillo = ProductoMenu.objects.create(**validated_data)
                for ing in ingredientes_data:
                    ProductoMenu_ArticuloInventario.objects.create(
                        idProductoMenu=nuevo_platillo,
                        idArticuloInventario=ing['idArticuloInventario'],
                        cantidad_usada=ing['cantidad_usada']
                    )
                return nuevo_platillo
        except Exception as e:
            if 'unique' in str(e).lower() and 'nombre' in str(e):
                raise serializers.ValidationError({"nombre": f"Ya existe un platillo con el nombre '{validated_data.get('nombre')}'."})
            raise serializers.ValidationError({"detail": str(e)})

    def update(self, instance, validated_data):
        ingredientes_data = validated_data.pop('productomenu_articuloinventario_set', None)
        
        try:
            with transaction.atomic():
                instance.nombre = validated_data.get('nombre', instance.nombre)
                instance.precio = validated_data.get('precio', instance.precio)
                instance.tiempoPreparacion = validated_data.get('tiempoPreparacion', instance.tiempoPreparacion)
                instance.categoria = validated_data.get('categoria', instance.categoria)
                instance.disponible = validated_data.get('disponible', instance.disponible)
                instance.save()

                if ingredientes_data is not None:
                    # Reemplazar por completo los ingredientes (Lógica de tu vista editar_platillo)[cite: 6]
                    ProductoMenu_ArticuloInventario.objects.filter(idProductoMenu=instance).delete()
                    for ing in ingredientes_data:
                        ProductoMenu_ArticuloInventario.objects.create(
                            idProductoMenu=instance,
                            idArticuloInventario=ing['idArticuloInventario'],
                            cantidad_usada=ing['cantidad_usada']
                        )
            return instance
        except Exception as e:
            if 'unique' in str(e).lower() and 'nombre' in str(e):
                raise serializers.ValidationError({"nombre": f"Ya existe un platillo con el nombre '{validated_data.get('nombre')}'."})
            raise serializers.ValidationError({"detail": str(e)})
        
# Serializador para la vista de historial de facturas
class FacturaHistorialSerializer(serializers.ModelSerializer):
    # Obtenemos el nombre del cliente a través de la relación de la llave foránea
    cliente_nombre = serializers.CharField(source='idCliente.nombre', read_only=True)
    monto_con_iva = serializers.SerializerMethodField()

    class Meta:
        model = Pedido
        fields = [
            'idPedido', 
            'fecha', 
            'cliente_nombre', 
            'montoTotal', 
            'monto_con_iva', 
            'estado_factura', 
            'estadoDePago'
        ]

    def get_monto_con_iva(self, obj):
        # Multiplicamos el monto original por 1.15 para incluir el IVA
        return round(float(obj.montoTotal) * 1.15, 2)


class AnularFacturaSerializer(serializers.Serializer):
    motivo_anulacion = serializers.ChoiceField(
        choices=[
            ('error_cobro', 'Error de cobro / Refacturación'),
            ('rechazo', 'Comida devuelta / Desperdicio'),
            ('duplicado', 'Pedido duplicado por error')
        ],
        error_messages={
            'invalid_choice': 'Debe seleccionar un motivo válido para la anulación.',
            'required': 'El motivo de anulación es obligatorio.'
        }
    )

class PlatilloColaSerializer(serializers.ModelSerializer):
    idPedido_Platillo = serializers.IntegerField(source='idPedido_ProductoMenu')
    nombre = serializers.CharField(source='idProductoMenu.nombre')
    tiempoPreparacion = serializers.IntegerField(source='idProductoMenu.tiempoPreparacion')

    class Meta:
        model = Pedido_ProductoMenu
        fields = ['idPedido_Platillo', 'nombre', 'estado', 'cantidad', 'tiempoPreparacion']


class PedidoColaSerializer(serializers.Serializer):
    idPedido = serializers.IntegerField()
    fecha = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    metodoPago = serializers.CharField()
    nombre_cliente = serializers.CharField(source='nombre')  # Creado por el AS de la consulta RAW
    idMesa_id = serializers.IntegerField(allow_null=True)
    montoTotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    platillos = serializers.SerializerMethodField()
    puede_facturar = serializers.SerializerMethodField()
    puede_eliminar = serializers.SerializerMethodField()

    def get_platillos(self, obj):
        # Obtenemos los platillos pre-procesados desde el contexto de la vista
        platillos_por_pedido = self.context.get('platillos_por_pedido', {})
        items = platillos_por_pedido.get(obj.idPedido, [])
        return PlatilloColaSerializer(items, many=True).data

    def get_puede_facturar(self, obj):
        platillos_por_pedido = self.context.get('platillos_por_pedido', {})
        items = platillos_por_pedido.get(obj.idPedido, [])
        return len(items) > 0 and all(item.estado == 'Servido' for item in items)

    def get_puede_eliminar(self, obj):
        platillos_por_pedido = self.context.get('platillos_por_pedido', {})
        items = platillos_por_pedido.get(obj.idPedido, [])
        # Un pedido es eliminable si todos sus ítems están 'Registrado'
        # o si están 'Listo' pero son productos sin tiempo de cocción (bebidas, etc.)
        return len(items) > 0 and all(
            item.estado == 'Registrado' or 
            (getattr(item.idProductoMenu, 'tiempoPreparacion', 0) == 0 and item.estado == 'Listo')
            for item in items
        )
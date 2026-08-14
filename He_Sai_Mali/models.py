from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from simple_history.models import HistoricalRecords

# 1. Modelo Sucursal
class Sucursal(models.Model):
    idSucursal = models.AutoField(primary_key=True)
    nombre_comercial = models.CharField(max_length=100, unique=True)
    numero_ruc = models.CharField(max_length=20, blank=True, null=True) 
    municipio = models.CharField(max_length=100)
    direccion_exacta = models.TextField()
    telefono = models.CharField(max_length=20, blank=True, null=True)
    numero_matricula_municipal = models.CharField(max_length=50, blank=True, null=True) 
    
    # Índice añadido: para filtrar las sucursales activas
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.nombre_comercial} - {self.municipio}"

    class Meta:
        db_table = 'Sucursal'

# Adaptar los usuarios admin creados por Django
class EmpleadoManager(BaseUserManager):
    def create_user(self, usuario, contrasena=None, **extra_fields):
        if not usuario:
            raise ValueError('El usuario es obligatorio')
        user = self.model(usuario=usuario, **extra_fields)
        user.set_password(contrasena)
        user.save(using=self._db)
        return user

    def create_superuser(self, usuario, contrasena=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(usuario, contrasena, **extra_fields)

# 1. Modelo Empleado
class Empleado(AbstractBaseUser, PermissionsMixin):
    idEmpleado = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT, null=True, blank=True)

    nombre = models.CharField(max_length=40)
    apellido = models.CharField(max_length=60)
    telefono = models.IntegerField(unique=True)
    correo = models.EmailField(unique=True)
    cedula = models.CharField(max_length=16, unique=True)
    # Índice añadido: Útil si hacemos búsquedas por rol (ej: Empleado.objects.filter(rol='Mesero'))
    rol = models.CharField(max_length=20, db_index=True)
    usuario = models.CharField(max_length=30, unique=True)

    # Índice añadido: Para el login o listados de personal activo
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = EmpleadoManager()

    USERNAME_FIELD = 'usuario' 
    
    REQUIRED_FIELDS = ['nombre','apellido', 'telefono','correo','cedula','rol']

    def __str__(self):
        return self.usuario

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True
    
    class Meta:
        db_table = 'Empleado'

# --- Modelo para auditoría de inicios de sesión y dispositivos ---
class RegistroSesion(models.Model):
    idRegistro = models.AutoField(primary_key=True)
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    # Índice añadido: Las auditorías siempre se ordenan o filtran por fecha
    fecha_login = models.DateTimeField(default=timezone.now, db_index=True)
    fecha_logout = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.empleado.usuario} - IP: {self.ip_address}"

    class Meta:
        db_table = 'RegistroSesion'

# 2. Modelo ProductoMenu
class ProductoMenu(models.Model):
    idProductoMenu = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    # Índice añadido: Muy común cargar el menú por categorías (Bebidas, Postres, etc.)
    categoria = models.CharField(max_length=20, db_index=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    tiempoPreparacion = models.IntegerField()
    # Índice añadido: Para mostrar solo lo que hay disponible en la app/caja
    disponible = models.BooleanField(default=1, db_index=True)

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = 'ProductoMenu'

# 3. Modelo Cliente
class Cliente(models.Model):
    idCliente = models.AutoField(primary_key=True)
    tipoCliente = models.CharField(max_length=10)
    nombre = models.CharField(max_length=100)
    # Índice añadido: Búsqueda rápida de clientes al momento de facturar
    identificacion = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    telefono = models.IntegerField(blank=True, null=True)
    correo = models.EmailField(max_length=100, blank=True, null=True)
    direccion = models.CharField(max_length=1000,blank=True, null=True)

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = 'Cliente'

# 4. Modelo Mesa
class Mesa(models.Model):
    idMesa = models.IntegerField(primary_key=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, null=True, blank=True)
    capacidad = models.IntegerField()
    # Índice añadido: Para que el sistema sepa rapidísimo qué mesas están libres
    ocupada = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"Mesa {self.idMesa} ({self.ocupada})"

    class Meta:
        db_table = 'Mesa'
        unique_together = ('idMesa', 'sucursal')

# 5. Modelo Proveedor (Se mantiene igual)
class Proveedor(models.Model):
    idProveedor = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    telefono = models.IntegerField(blank=True, null=True)
    direccion = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre
    
    class Meta:
        db_table = 'Proveedor'

# 6. Modelo ArticuloInventario
class ArticuloInventario(models.Model):
    idArticuloInventario = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, null=True, blank=True)
    nombre = models.CharField(max_length=100)
    unidad_de_medida = models.CharField(max_length=20)
    stock = models.DecimalField(max_digits=10, decimal_places=2)
    # Índice añadido: Por si filtramos entre "Insumos", "Bebidas", "Limpieza", etc.
    tipoArticulo = models.CharField(max_length=20, db_index=True)
    ubicacion = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"{self.nombre} ({self.stock} {self.unidad_de_medida})"
    
    class Meta:
        db_table = 'ArticuloInventario'
        unique_together = ('nombre', 'sucursal')
    
# 7. Modelo Pedido
class Pedido(models.Model):
    idPedido = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT, null=True, blank=True)
    # Índice añadido: Fundamental. Todos los reportes de ventas se agruparán por fecha
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    montoTotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    metodoPago = models.CharField(max_length=50, blank=True, null=True)
    
    idCliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    idMesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True)
    estadoDePago = models.BooleanField(default=False, blank=True, null=True)

    ESTADOS_FACTURA = [
        ('VIGENTE', 'Vigente'),
        ('ANULADA', 'Anulada'),
    ]
    
    # Índice añadido: Para calcular ventas sumando solo facturas 'VIGENTES'
    estado_factura = models.CharField(
        max_length=10, 
        choices=ESTADOS_FACTURA, 
        default='VIGENTE',
        verbose_name="Estado de la Factura",
        db_index=True
    )
    
    def __str__(self):
        return f"pedido N°{self.idPedido}"

    class Meta:
        db_table = 'Pedido'

# 8. Modelo Intermedio: Pedido_ProductoMenu
class Pedido_ProductoMenu(models.Model):
    idPedido_ProductoMenu = models.AutoField(primary_key=True)
    idPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    idProductoMenu = models.ForeignKey(ProductoMenu, on_delete=models.CASCADE)
    
    ESTADOS = [
        ('Registrado', 'Registrado'),
        ('Listo', 'Listo'),
        ('Servido', 'Servido'),
        ('Facturado', 'Facturado'),
        ('Merma', 'Merma'),
        ('Anulado', 'Anulado'),
    ]
    # Índice añadido: VITAL. La pantalla de cocina estará filtrando todo el tiempo por 'Registrado'
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Registrado', db_index=True)
    cantidad = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.cantidad}x {self.idProductoMenu.nombre} en Pedido {self.idPedido.idPedido} ({self.estado})"

    class Meta:
        db_table = 'Pedido_ProductoMenu'

# 9. Modelo Intermedio: Empleado_Pedido (Se mantiene igual, unique_together genera índice)
class Empleado_Pedido(models.Model):
    idEmpleado_Pedido = models.AutoField(primary_key=True)
    idEmpleado = models.ForeignKey(Empleado, on_delete=models.PROTECT)
    idPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE)
    fechaAsignacion = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.idEmpleado.usuario} atiende Pedido N°{self.idPedido.idPedido}"

    class Meta:
        unique_together = (('idEmpleado', 'idPedido'),) 
        db_table = 'Empleado_Pedido'

# 10. Modelo Intermedio: ProductoMenu_ArticuloInventario (Se mantiene igual)
class ProductoMenu_ArticuloInventario(models.Model):
    idProductoMenu_ArticuloInventario = models.AutoField(primary_key=True)
    idProductoMenu = models.ForeignKey(ProductoMenu, on_delete=models.CASCADE)
    idArticuloInventario = models.ForeignKey(ArticuloInventario, on_delete=models.CASCADE)
    cantidad_usada = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Receta: {self.ProductoMenu.nombre} usa {self.cantidad_usada} de {self.ArticuloInventario.nombre}"
    
    class Meta:
        unique_together = ('idProductoMenu', 'idArticuloInventario')
        db_table = 'ProductoMenu_ArticuloInventario'
    
# 11. Modelo Intermedio: ArticuloInventario_Proveedor
class ArticuloInventario_Proveedor(models.Model):
    idArticuloInventario_Proveedor = models.AutoField(primary_key=True)
    fechaCompra = models.DateTimeField(default=timezone.now, db_index=True) # Añadido para reportes de gastos
    precioCompra = models.DecimalField(max_digits=10, decimal_places=2)
    cantidadCompra = models.DecimalField(max_digits = 10, decimal_places=2)
    idArticuloInventario = models.ForeignKey(ArticuloInventario, on_delete=models.CASCADE)
    idProveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.ArticuloInventario.nombre} suministrado por {self.proveedor.nombre}"
    
    class Meta:
        db_table = 'ArticuloInventario_Proveedor'


# --- VISTAS DE BASE DE DATOS ---
class VistaPedidosCocina(models.Model):
    id = models.IntegerField(primary_key=True, db_column='idPedido_ProductoMenu') 
    cantidad = models.IntegerField()
    id_pedido = models.IntegerField(db_column='idPedido_id')
    nombre_platillo = models.CharField(max_length=100)
    fecha = models.DateTimeField()
    nombre_cliente = models.CharField(max_length=100)
    id_mesa = models.IntegerField(db_column='idMesa_id', null=True)

    class Meta:
        managed = False
        db_table = 'vw_pedidos_cocina'

class VistaAlertasStock(models.Model):
    id = models.IntegerField(primary_key=True, db_column='idArticuloInventario')
    ingrediente = models.CharField(max_length=100)
    stock = models.DecimalField(max_digits=10, decimal_places=2)
    unidad_de_medida = models.CharField(max_length=20)
    porciones_posibles = models.IntegerField() 

    class Meta:
        managed = False
        db_table = 'vw_alertas_stock'

# --- NUEVO: BITÁCORA GENERAL DE AUDITORÍA ---
class AuditoriaGeneral(models.Model):
    id_auditoria = models.AutoField(primary_key=True)
    
    # Índice añadido: Como no usamos ForeignKey aquí 
    # Django no le pone índice automático. Se lo ponemos manual para buscar rápido qué hizo un empleado.
    empleado_id = models.IntegerField(null=True, blank=True, db_index=True)
    usuario_nombre = models.CharField(max_length=100)
    rol = models.CharField(max_length=50)
    sucursal_id = models.IntegerField(null=True, blank=True, db_index=True)
    
    # Índices añadidos: Si queremos ver "Todo lo que pasó en Facturación" o "Todos los Delete"
    modulo = models.CharField(max_length=50, db_index=True) 
    accion = models.CharField(max_length=30, db_index=True) 
    
    detalles = models.TextField() 
    
    # Índice añadido: Fundamental porque tenemos un ordering=['-fecha_accion'] en Meta
    fecha_accion = models.DateTimeField(default=timezone.now, db_index=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'AuditoriaGeneral'
        ordering = ['-fecha_accion']

    def __str__(self):
        return f"[{self.fecha_accion.strftime('%Y-%m-%d %H:%M')}] {self.usuario_nombre} - {self.modulo}: {self.accion}"
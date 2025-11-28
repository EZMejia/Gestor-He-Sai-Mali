from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

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

    nombre = models.CharField(max_length=40)
    apellido = models.CharField(max_length=60)
    telefono = models.IntegerField(unique=True)
    correo = models.EmailField(unique=True)
    cedula = models.CharField(max_length=16, unique=True)
    rol = models.CharField(max_length=20)
    usuario = models.CharField(max_length=30, unique=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = EmpleadoManager()

    USERNAME_FIELD = 'usuario' 
    
    REQUIRED_FIELDS = ['apellido', 'nombre','correo','cedula','rol']

    def __str__(self):
        return self.usuario

    # Necesario para admin
    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True
    
    class Meta:
        db_table = 'Empleado'

# 2. Modelo ProductoMenu
class ProductoMenu(models.Model):
    idProductoMenu = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    categoria = models.CharField(max_length=20)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    tiempoPreparacion = models.IntegerField()
    # Agregado
    disponible = models.BooleanField(default=1)

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = 'ProductoMenu'

# 3. Modelo Cliente
class Cliente(models.Model):
    idCliente = models.AutoField(primary_key=True)
    tipoCliente = models.CharField(max_length=10)
    nombre = models.CharField(max_length=100)
    identificacion = models.CharField(max_length=20, blank=True, null=True)
    telefono = models.IntegerField(blank=True, null=True)
    correo = models.EmailField(max_length=100, blank=True, null=True)

    # Agregado
    direccion = models.CharField(max_length=1000,blank=True, null=True)

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = 'Cliente'

# 4. Modelo Mesa
class Mesa(models.Model):
    idMesa = models.IntegerField(primary_key=True)
    capacidad = models.IntegerField()
    ocupada = models.BooleanField(default=False)

    def __str__(self):
        return f"Mesa {self.idMesa} ({self.ocupada})"

    class Meta:
        db_table = 'Mesa'

# 5. Modelo Proveedor
class Proveedor(models.Model):
    idProveedor = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    telefono = models.IntegerField(blank=True, null=True)
    direccion = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre
    
    class Meta:
        db_table = 'Proveedor'

# Se cambio Ingrediente -> ArticuloInventario
# 6. Modelo Ingrediente
class ArticuloInventario(models.Model):
    idArticuloInventario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    unidad_de_medida = models.CharField(max_length=20)
    stock = models.DecimalField(max_digits=10, decimal_places=2)

    # Agregado
    tipoArticulo = models.CharField(max_length=20)
    ubicacion = models.CharField(max_length=20, blank=True, null=True)


    def __str__(self):
        return f"{self.nombre} ({self.stock} {self.unidad_de_medida})"
    
    class Meta:
        db_table = 'ArticuloInventario'
    
# 7. Modelo Pedido
class Pedido(models.Model):
    idPedido = models.AutoField(primary_key=True)
    fecha = models.DateTimeField(default=timezone.now)
    montoTotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    metodoPago = models.CharField(max_length=50, blank=True, null=True)
    
    idCliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    idMesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True)

    # Agregado
    estadoDePago = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return f"pedido N°{self.idPedido}"

    class Meta:
        db_table = 'Pedido'

# 8. Modelo Intermedio: Pedido_ProductoMenu (Solicita)
class Pedido_ProductoMenu(models.Model):
    idPedido_ProductoMenu = models.AutoField(primary_key=True)
    # FK IdPedido
    idPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    
    # FK IdProductoMenu
    idProductoMenu = models.ForeignKey(ProductoMenu, on_delete=models.CASCADE)
    
    # Campo 'Estado'
    ESTADOS = [
        ('Registrado', 'Registrado'),
        ('Listo', 'Listo'),
        ('Servido', 'Servido'),
        ('Facturado', 'Facturado'),
    ]
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Registrado')
    cantidad = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.cantidad}x {self.idProductoMenu.nombre} en Pedido {self.idPedido.idPedido} ({self.estado})"

    class Meta:
        db_table = 'Pedido_ProductoMenu'

# 9. Modelo Intermedio: Empleado_Pedido (Atiende)
class Empleado_Pedido(models.Model):
    idEmpleado_Pedido = models.AutoField(primary_key=True)

    # FK IdEmpleado (Mesero)
    idEmpleado = models.ForeignKey(Empleado, on_delete=models.PROTECT)
    
    # FK IdPedido
    idPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE)
    
    fechaAsignacion = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.idEmpleado.usuario} atiende Pedido N°{self.idPedido.idPedido}"

    class Meta:
        # Clave compuesta (Empleado, Pedido)
        unique_together = (('idEmpleado', 'idPedido'),) 
        db_table = 'Empleado_Pedido'

# 10. Modelo Intermedio: ProductoMenu_Ingrediente (contiene)
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
    
# 11. Modelo Intermedio: Ingrediente_Proveedor (suministra)
class ArticuloInventario_Proveedor(models.Model):
    idArticuloInventario_Proveedor = models.AutoField(primary_key=True)

    fechaCompra = models.DateTimeField(default=timezone.now)
    precioCompra = models.DecimalField(max_digits=10, decimal_places=2)

    # Agregado
    cantidadCompra = models.DecimalField(max_digits = 10, decimal_places=2)

    idArticuloInventario = models.ForeignKey(ArticuloInventario, on_delete=models.CASCADE)
    idProveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    def __str__(self):
        return f"{self.ArticuloInventario.nombre} suministrado por {self.proveedor.nombre}"
    
    class Meta:
        db_table = 'ArticuloInventario_Proveedor'
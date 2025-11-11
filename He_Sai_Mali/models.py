from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

# Create your models here.
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
    IdEmpleado = models.AutoField(primary_key=True)

    Nombre = models.CharField(max_length=20)
    Apellido = models.CharField(max_length=20)
    Telefono = models.CharField(max_length=11, blank=True, null=True)
    Correo = models.EmailField(unique=True)
    Cedula = models.CharField(max_length=16, unique=True)
    Rol = models.CharField(max_length=50)
    Usuario = models.CharField(max_length=50, unique=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = EmpleadoManager()

    USERNAME_FIELD = 'Usuario' 
    
    REQUIRED_FIELDS = ['Apellido', 'Nombre','Correo','Cedula','Rol']

    def __str__(self):
        return self.Usuario

    # Necesario para admin
    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True
    
    class Meta:
        db_table = 'Empleado'

# 2. Modelo Platillo
class Platillo(models.Model):
    IdPlatillo = models.AutoField(primary_key=True)
    Nombre = models.CharField(max_length=100, unique=True)
    Descripcion = models.TextField(blank=True, null=True)
    Precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.Nombre

    class Meta:
        db_table = 'Platillo'

# 10. Modelo Cliente
class Cliente(models.Model):
    IdCliente = models.AutoField(primary_key=True)
    Nombre = models.CharField(max_length=100)
    Telefono = models.CharField(max_length=15, blank=True, null=True)
    Correo = models.EmailField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.Nombre

    class Meta:
        db_table = 'Cliente'

# 11. Modelo Mesa
class Mesa(models.Model):
    IdMesa = models.AutoField(primary_key=True)
    Capacidad = models.IntegerField(default=4)
    Ocupada = models.BooleanField(default=False)

    def __str__(self):
        return f"Mesa {self.NumeroMesa} ({self.Ocupada})"

    class Meta:
        db_table = 'Mesa'

# 3. Modelo Pedido
class Pedido(models.Model):
    IdPedido = models.AutoField(primary_key=True)
    Fecha = models.DateTimeField(default=timezone.now)
    MontoTotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    MetodoPago = models.CharField(max_length=50, blank=True, null=True)
    
    IdCliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    IdMesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"pedido N°{self.IdPedido}"

    class Meta:
        db_table = 'Pedido'

# 4. Modelo Intermedio: Pedido_Platillo (Solicita)
class Pedido_Platillo(models.Model):
    IdPedido_Platillo = models.AutoField(primary_key=True)
    # FK IdPedido
    IdPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    
    # FK IdPlatillo
    IdPlatillo = models.ForeignKey(Platillo, on_delete=models.PROTECT)
    
    # Campo 'Estado'
    ESTADOS = [
        ('Registrado', 'Registrado'),
        ('Listo', 'Listo'),
        ('Servido', 'Servido'),
        ('Facturado', 'Facturado'),
    ]
    Estado = models.CharField(max_length=20, choices=ESTADOS, default='Registrado')
    Cantidad = models.IntegerField(default=1) # Añadido, ya que un platillo puede pedirse varias veces.

    def __str__(self):
        return f"{self.Cantidad}x {self.IdPlatillo.Nombre} en Pedido {self.IdPedido.IdPedido} ({self.Estado})"

    class Meta:
        # Clave compuesta (Pedido, Platillo)
        db_table = 'Pedido_Platillo'

# 5. Modelo Intermedio: Empleado_Pedido (Atiende)
class Empleado_Pedido(models.Model):
    IdEmpleado_Pedido = models.AutoField(primary_key=True)

    # FK IdEmpleado (Mesero)
    IdEmpleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name='pedidos_atendidos')
    
    # FK IdPedido
    IdPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='atendido_por')
    
    FechaAsignacion = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.IdEmpleado.Usuario} atiende Pedido N°{self.IdPedido.IdPedido}"

    class Meta:
        # Clave compuesta (Empleado, Pedido)
        unique_together = (('IdEmpleado', 'IdPedido'),) 
        db_table = 'Empleado_Pedido'

# 6. Modelo Proveedor
class Proveedor(models.Model):
    IdProveedor = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    telefono = models.CharField(max_length=15, blank=True, unique=True)
    direccion = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre
    
    class Meta:
        db_table = 'Proveedor'

# 7. Modelo Ingrediente
class Ingrediente(models.Model):
    IdIngrediente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)
    unidad_de_medida = models.CharField(max_length=20)
    stock = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.nombre} ({self.stock} {self.unidad_de_medida})"
    
    class Meta:
        db_table = 'Ingrediente'
    
# 8. Modelo Intermedio: Platillo_Ingrediente (contiene)
class Platillo_Ingrediente(models.Model):
    IdPlatillo_Ingrediente = models.AutoField(primary_key=True)

    IdPlatillo = models.ForeignKey(Platillo, on_delete=models.CASCADE)
    IdIngrediente = models.ForeignKey(Ingrediente, on_delete=models.PROTECT)
    cantidad_usada = models.DecimalField(max_digits=10, decimal_places=2) # Cantidad necesaria

    def __str__(self):
        return f"Receta: {self.platillo.nombre} usa {self.cantidad_usada} de {self.ingrediente.nombre}"
    
    class Meta:
        unique_together = ('IdPlatillo', 'IdIngrediente')
        db_table = 'Platillo_Ingrediente'
    
# 9. Modelo Intermedio: Ingrediente_Proveedor (suministra)
class Ingrediente_Proveedor(models.Model):
    IdIngrediente_Proveedor = models.AutoField(primary_key=True)

    IdIngrediente = models.ForeignKey(Ingrediente, on_delete=models.CASCADE)
    IdProveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.ingrediente.nombre} suministrado por {self.proveedor.nombre}"
    
    class Meta:
        unique_together = ('IdIngrediente', 'IdProveedor')
        db_table = 'Ingrediente_Proveedor'
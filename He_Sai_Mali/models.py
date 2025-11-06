from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

# Create your models here.
class EmpleadoManager(BaseUserManager):
    def create_user(self, correo, contrasena=None, **extra_fields):
        if not correo:
            raise ValueError('El correo es obligatorio')
        correo = self.normalize_email(correo)
        user = self.model(correo=correo, **extra_fields)
        user.set_password(contrasena)
        user.save(using=self._db)
        return user

    def create_superuser(self, correo, contrasena=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(correo, contrasena, **extra_fields)

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
    
    # Agregar cedula, rol al volver a crear la tabla
    REQUIRED_FIELDS = ['Apellido', 'Nombre','Correo']

    def __str__(self):
        return self.Usuario

    # Necesario para admin
    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True
    
    class Meta:
        db_table = 'Empleado'

class Platillo(models.Model):
    IdPlatillo = models.AutoField(primary_key=True)
    Nombre = models.CharField(max_length=100)
    Descripcion = models.TextField(blank=True, null=True)
    Precio = models.DecimalField(max_digits=10, decimal_places=2)
    # Si hay una FK 'Usa' que apunta a ingredientes, deberías crear ese modelo también.

    def __str__(self):
        return self.Nombre

    class Meta:
        db_table = 'Platillo'
        verbose_name = 'Platillo'
        verbose_name_plural = 'Platillos'

# ---

## 3. Modelo Pedido

class Pedido(models.Model):
    # Campos de la tabla Pedido
    IdPedido = models.AutoField(primary_key=True)
    Fecha = models.DateTimeField(default=timezone.now)
    MontoTotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    MetodoPago = models.CharField(max_length=50, blank=True, null=True)
    
    # FK IdPersona (Nombre del Cliente, según tu requerimiento)
    # Se recomienda usar un modelo 'Cliente', pero lo dejaré como CharField por simplicidad si no lo tienes.
    IdPersona = models.CharField(max_length=100, verbose_name="Nombre Cliente") 

    def __str__(self):
        return f"Pedido N°{self.IdPedido} - Cliente: {self.IdPersona}"

    class Meta:
        db_table = 'Pedido'
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'

# ---

## 4. Modelo Intermedio: Pedido_Platillo (Solicita)

# Representa los ítems dentro de un pedido, clave para el seguimiento de estado.
class Pedido_Platillo(models.Model):
    # FK IdPedido
    IdPedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    
    # FK IdPlatillo
    IdPlatillo = models.ForeignKey(Platillo, on_delete=models.PROTECT)
    
    # Campo 'Estado'
    ESTADOS = [
        ('Registrado', 'Registrado'),
        ('Listo', 'Listo para servir'),
        ('Servido', 'Servido'),
        ('Facturado', 'Facturado'),
    ]
    Estado = models.CharField(max_length=20, choices=ESTADOS, default='Registrado')
    Cantidad = models.IntegerField(default=1) # Añadido, ya que un platillo puede pedirse varias veces.

    def __str__(self):
        return f"{self.Cantidad}x {self.IdPlatillo.Nombre} en Pedido {self.IdPedido.IdPedido} ({self.Estado})"

    class Meta:
        # Clave compuesta (Pedido, Platillo) - No permitimos duplicados exactos.
        unique_together = (('IdPedido', 'IdPlatillo'),) 
        db_table = 'Pedido_Platillo'
        verbose_name = 'Ítem de Pedido'
        verbose_name_plural = 'Ítems de Pedido'

# ---

## 5. Modelo Intermedio: Empleado_Pedido (Atiende)

# Representa qué empleado (Mesero) atiende un pedido.
class Empleado_Pedido(models.Model):
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
        verbose_name = 'Asignación de Empleado a Pedido'
        verbose_name_plural = 'Asignaciones de Empleados a Pedidos'
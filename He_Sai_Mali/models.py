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
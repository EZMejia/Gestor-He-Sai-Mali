from django.contrib import admin
from .models import Empleado

# Register your models here.
@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('Correo', 'Usuario', 'Nombre', 'Rol', 'is_staff')
    search_fields = ('Correo', 'Usuario', 'Nombre')
    list_filter = ('Rol', 'is_staff')
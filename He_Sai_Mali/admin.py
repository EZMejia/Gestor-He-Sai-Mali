from django.contrib import admin
from .models import Empleado

# Register your models here.
@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('correo', 'usuario', 'nombre', 'rol', 'is_staff')
    search_fields = ('correo', 'usuario', 'nombre')
    list_filter = ('rol', 'is_staff')
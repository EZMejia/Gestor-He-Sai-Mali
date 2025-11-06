from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test

from django.contrib.auth import login, authenticate, logout
from django.contrib import messages

from .models import *
from django.db.models import F, Sum, Case, When

import re

from .decorators import es_rol

# Create your views here.
def main(request):
    return render(request, 'He_Sai_Mali/main.html')

def pedido(request):
    return render(request, 'He_Sai_Mali/pedido.html')

def registro(request):
    if request.method == 'POST':
        # --- Obtener datos ---
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        telefono = request.POST.get('telefono', '').strip() or None
        correo = request.POST.get('correo', '').strip()
        cedula = request.POST.get('cedula', '').strip() or None
        rol = request.POST.get('rol', '').strip()
        contrasena1 = request.POST.get('contrasena1')
        contrasena2 = request.POST.get('contrasena2')

        # --- Validaciones ---
        errores = []

        if contrasena1 != contrasena2:
            errores.append("Las contraseñas no coinciden.")
        if Empleado.objects.filter(Correo=correo).exists():
            errores.append("Este correo ya está registrado.")

        # --- Generar Usuario ---
        usuario = None
        if nombre and apellido and rol:
            def primeras_dos(palabra):
                return re.sub(r'[^a-zA-Z]', '', palabra).lower()[:2]
            base = primeras_dos(nombre) + primeras_dos(apellido) + rol.capitalize() + "HSM"
            usuario = base
            contador = 1
            while Empleado.objects.filter(Usuario=usuario).exists():
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
        empleado = Empleado(
            Nombre=nombre or None,
            Apellido=apellido or None,
            Telefono=telefono,
            Correo=correo,
            Cedula=cedula,
            Rol=rol or None,
            Usuario=usuario
        )
        empleado.set_password(contrasena1)
        empleado.save()

        return redirect('login')

    return render(request, 'He_Sai_Mali/registro.html')

def login_view(request):
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

@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_mesero(request):
    return render(request, 'He_Sai_Mali/pedidos.html')

@user_passes_test(es_rol("Mesero"), login_url='login')
def vista_registrarpedido(request):
    return render(request, 'He_Sai_Mali/registrarpedido.html')

@user_passes_test(es_rol("Cocinero"), login_url='login')
def vista_cocinero(request):
    return render(request, 'He_Sai_Mali/cocina.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
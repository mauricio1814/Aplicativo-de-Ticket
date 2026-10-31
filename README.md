# Mesa de ayuda IT

Aplicación web de tickets con servidor en Python y base de datos SQLite. No necesita instalar librerías externas.

## Requisitos

- Python 3.10 o superior.
- Para abrirla desde otros dispositivos, todos deben estar en la misma red local.

## Iniciar en Windows (PowerShell)

Abre PowerShell en esta carpeta y ejecuta:

```powershell
python server.py
```

Si `python` no funciona, intenta `py server.py`. En el mismo equipo abre `http://localhost:8000`.

## Acceso por dirección IP (red local)

El servidor escucha en `0.0.0.0:8000`. Averigua la IPv4 del computador con `ipconfig` y desde otro dispositivo conectado a la misma red abre `http://IP_DEL_COMPUTADOR:8000`, por ejemplo `http://192.168.1.25:8000`.

Si Windows Firewall pregunta, permite Python en redes privadas. Si no pregunta y otro dispositivo no conecta, crea una regla de entrada para TCP puerto 8000 en el perfil Privado. No publiques este servidor en Internet.

## Iniciar desde WSL

1. Instala WSL y una distribución Linux, si aún no están instaladas.
2. Abre la terminal de la distribución y navega a la carpeta del proyecto montada bajo `/mnt/c`:

```bash
cd "/mnt/c/Users/alvar/Documents/Trabajos U/Noveno Semestre/Telematica/Proyecto Ticket"
python3 server.py
```

En el mismo Windows abre `http://localhost:8000`. Para acceso desde otro dispositivo, usa la IPv4 de Windows obtenida con `ipconfig` y permite el puerto TCP 8000 en Windows Firewall. La disponibilidad de la IP de WSL desde la red puede variar por la configuración de WSL; para una presentación en la red local, es más sencillo ejecutar `python server.py` directamente en Windows.

## Cuentas de demostración

- Usuario: `usuario@demo.com` / `usuario123`
- Técnico: `tecnico@demo.com` / `tecnico123`

La base de datos se crea automáticamente en `data/mesa_ayuda.db`. Conserva tickets, usuarios iniciales y actualizaciones aunque se reinicie el servidor.

## Alcance del proyecto académico

El servidor es para desarrollo y demostración en una red controlada. Las sesiones se guardan en memoria, por lo que se cierran al reiniciar Python. Para un sistema real se requiere HTTPS, gestión segura de usuarios, copias de seguridad y despliegue endurecido. No uses datos personales reales ni expongas el puerto directamente a Internet.

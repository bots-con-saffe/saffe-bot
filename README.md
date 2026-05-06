# Saffe Bot

Bot de Discord desarrollado en Python con `discord.py` para la gestión de una guild de **Albion Online**. Automatiza la bienvenida de nuevos miembros, la creación de canales de voz temporales, la organización de actividades con listas de inscripción y herramientas de moderación.

---

## Tabla de contenidos

- [Requisitos](#requisitos)
- [Instalación y configuración](#instalación-y-configuración)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Módulos y funcionalidades](#módulos-y-funcionalidades)
  - [Bienvenida automática](#1-bienvenida-automática-cogsbienvenidapy)
  - [Canales de voz temporales](#2-canales-de-voz-temporales-cogscrear_canalespy)
  - [Sistema de actividades y pings](#3-sistema-de-actividades-y-pings-cogspingspy)
  - [Asignación de roles](#4-asignación-de-roles-cogsrolespy)
  - [Moderación](#5-moderación-cogsmoderaciónpy)
  - [Administración del bot](#6-administración-del-bot-bot_saffepy)
- [Archivo de datos: actividades.json](#archivo-de-datos-actividadesjson)
- [Resumen de comandos](#resumen-de-comandos)

---

## Requisitos

- Python 3.10+
- Librería `discord.py` (con soporte para slash commands y threads)
- Librería `python-dotenv`

## Instalación y configuración

1. Clona el repositorio.
2. Crea un archivo `.env` en la raíz con el token de tu bot:
   ```
   DISCORD_TOKEN=tu_token_aqui
   ```
3. Instala las dependencias:
   ```bash
   pip install discord.py python-dotenv
   ```
4. Ejecuta el bot:
   ```bash
   python bot_saffe.py
   ```

---

## Estructura del proyecto

```
saffe-bot/
├── bot_saffe.py          # Punto de entrada principal del bot
├── actividades.json      # Plantillas de actividades persistidas en disco
├── .env                  # Token del bot (no incluir en el repositorio)
└── cogs/
    ├── bienvenida.py     # Bienvenida y asignación automática de rol
    ├── crear_canales.py  # Canales de voz temporales y dinámicos
    ├── pings.py          # Sistema de actividades e inscripciones
    ├── roles.py          # Asignación de paquetes de roles
    └── moderacion.py     # Herramientas de moderación
```

---

## Módulos y funcionalidades

### 1. Bienvenida automática (`cogs/bienvenida.py`)

Cuando un nuevo usuario se une al servidor, el bot le asigna automáticamente el rol **Scout**. Esto sirve como rol de entrada que distingue a los recién llegados.

- Si el rol `Scout` no existe en el servidor, el bot registra un aviso en consola.
- Si el bot no tiene permisos suficientes, informa del error 403.

**Comando de prueba:**

| Comando | Descripción |
|---|---|
| `!test_scout` | Simula la entrada de un nuevo miembro: quita y vuelve a asignar el rol Scout al autor del comando. Util para verificar que el flujo funciona correctamente. |

---

### 2. Canales de voz temporales (`cogs/crear_canales.py`)

Sistema de salas de voz dinámicas organizadas por tipo de contenido. Al iniciarse el bot, verifica que existan tres categorias en el servidor con sus respectivos canales lobby:

| Categoría | Canal lobby |
|---|---|
| Contenido PVE | `⚔️ Únete para PVE` |
| Contenido PVP | `🔴 Únete para PVP` |
| Avalonianas | `💎 Únete para Ava` |

Si alguno de estos lobbies no existe, el bot lo crea automáticamente.

**Funcionamiento:**

1. Cuando un miembro se une a un canal lobby, el bot crea automáticamente una sala de voz temporal con el nombre `[prefijo] de [nombre del usuario]` y mueve al miembro a ella.
2. El creador de la sala es el **líder** y obtiene permisos de gestión del canal (renombrar, cambiar permisos, etc.).
3. Si el líder abandona la sala, el siguiente miembro en la lista pasa a ser el nuevo líder automáticamente.
4. Cuando la sala queda vacía, el bot la elimina.

**Comandos del líder** (solo funcionan dentro de la sala temporal que el usuario lidera):

| Comando | Descripción |
|---|---|
| `!name [nuevo nombre]` | Cambia el nombre de la sala. Discord limita a 2 cambios cada 10 minutos. |
| `!limite [número]` | Establece el límite de usuarios de la sala. |
| `!lock` | Bloquea la sala para que nadie más pueda entrar. |
| `!unlock` | Vuelve a abrir la sala al público. |

---

### 3. Sistema de actividades y pings (`cogs/pings.py`)

Permite organizar actividades del juego (dungeons, mazmorras grupales, rastreos, etc.) con un sistema de inscripción por roles/puestos.

Las plantillas de actividades se guardan en el archivo `actividades.json` y persisten entre reinicios del bot.

**Flujo completo:**

1. Un administrador crea una plantilla de actividad definiendo los puestos que necesita.
2. Un moderador lanza un ping con esa plantilla, que genera un embed con todos los puestos vacíos.
3. El bot crea automáticamente un hilo asociado al embed donde los miembros se apuntan escribiendo el número del puesto que quieren.
4. El embed se actualiza en tiempo real con los nombres de los inscritos.
5. Al finalizar, un oficial puede cerrar la actividad con el comando `!callout`.

**Comandos:**

| Comando | Permisos | Descripción |
|---|---|---|
| `!crear_plantilla [nombre] [puesto1, puesto2, ...]` | Administrador | Crea o sobreescribe una plantilla de actividad. Los puestos se separan por comas. Ejemplo: `!crear_plantilla dungeon Tanque, Healer, Dps, Dps` |
| `!ping [tipo] [@rol_opcional] [id_mensaje_build] [info]` | Gestionar mensajes | Lanza un ping de actividad. Menciona al rol indicado y al rol `Miembro`. Puede adjuntar una imagen de build desde otro mensaje. |
| `!mass [mensaje]` | Gestionar mensajes | Desde dentro del hilo de una actividad, menciona a todos los inscritos. Útil para avisar de que se va a salir. |

**Lógica de inscripción dentro del hilo:**

- Escribir un número (ej: `2`) apunta al usuario en ese puesto. Si ya tenía otro puesto, lo libera.
- Escribir un número precedido de `-` (ej: `-2`) cancela la inscripción en ese puesto.
- Si un puesto ya está ocupado, el bot notifica al usuario por mensaje privado (o en el hilo si tiene los DMs cerrados).
- El hilo permanece activo durante **2 horas** (7200 segundos de timeout).

---

### 4. Asignación de roles (`cogs/roles.py`)

Permite a los moderadores asignar conjuntos de roles predefinidos a un usuario con un solo comando, en lugar de tener que asignarlos uno por uno.

**Paquetes disponibles:**

| Paquete | Roles que asigna |
|---|---|
| `miembro` | Miembro, Pve content, Pvp content |
| `miembroava` | Miembro, Pve content, Pvp content, Ava core |

**Comando:**

| Comando | Permisos | Descripción |
|---|---|---|
| `!rol [paquete] @usuario` | Gestionar roles | Asigna todos los roles del paquete indicado al usuario mencionado. El mensaje del moderador se borra automáticamente. |

Ejemplo: `!rol miembroava @NombreJugador`

---

### 5. Moderación (`cogs/moderacion.py`)

Herramientas de moderación para el servidor. Las acciones destructivas (kick y timeout) requieren confirmación mediante botones para evitar errores accidentales.

**Comandos:**

| Comando | Permisos | Descripción |
|---|---|---|
| `!clear [cantidad]` | Gestionar mensajes | Borra los últimos N mensajes del canal (por defecto 5). También disponible como `!borrar` y `!limpiar`. |
| `!callout` | Oficial / Guild Master | Cierra una actividad: marca el embed como FINALIZADA (cambia el color a rojo), menciona a todos los inscritos y archiva y bloquea el hilo. Solo funciona dentro del hilo de una actividad. |
| `!kick @usuario [motivo]` | Oficial / Guild Master | Muestra un mensaje de confirmación con botones. Si se confirma, expulsa al usuario del servidor. La confirmación caduca en 30 segundos. |
| `!timeout @usuario [minutos] [motivo]` | Oficial / Guild Master | Muestra un mensaje de confirmación con botones. Si se confirma, silencia al usuario durante el tiempo indicado. El bot verifica que el rango del objetivo sea inferior al suyo antes de proceder. |

---

### 6. Administración del bot (`bot_saffe.py`)

El archivo principal configura el bot con el prefijo `!` y los intents necesarios (estados de voz, contenido de mensajes y miembros). Carga todos los módulos de la carpeta `cogs/` automáticamente al arrancar.

**Comandos exclusivos del propietario del bot:**

| Comando | Descripción |
|---|---|
| `!reload [modulo]` | Recarga uno o todos los módulos en caliente sin necesidad de reiniciar el bot. Si no se especifica módulo, recarga todos. El mensaje del comando se borra automáticamente. |
| `!restart` | Reinicia el proceso completo del bot ejecutando de nuevo el script de Python. |

---

## Archivo de datos: actividades.json

Almacena las plantillas de actividades en formato JSON. El archivo se crea automáticamente si no existe. Viene pre-configurado con dos plantillas de ejemplo:

```json
{
    "grupales": ["Tanque", "Healer", "Sc", "Flamigero", "Badon", "invocador de luz", "prefora nieblas"],
    "rastreo": ["Tanque", "Healer", "Dps", "Dps", "Dps"]
}
```

Las plantillas se pueden añadir o modificar en cualquier momento con el comando `!crear_plantilla` sin necesidad de editar el archivo manualmente.

---

## Resumen de comandos

| Comando | Modulo | Permisos |
|---|---|---|
| `!test_scout` | Bienvenida | Todos |
| `!name [nombre]` | Canales | Lider de la sala |
| `!limite [num]` | Canales | Lider de la sala |
| `!lock` | Canales | Lider de la sala |
| `!unlock` | Canales | Lider de la sala |
| `!crear_plantilla [nombre] [puestos]` | Pings | Administrador |
| `!ping [tipo] ...` | Pings | Gestionar mensajes |
| `!mass [mensaje]` | Pings | Gestionar mensajes |
| `!rol [paquete] @usuario` | Roles | Gestionar roles |
| `!clear [cantidad]` | Moderación | Gestionar mensajes |
| `!callout` | Moderación | Oficial / Guild Master |
| `!kick @usuario [motivo]` | Moderación | Oficial / Guild Master |
| `!timeout @usuario [min] [motivo]` | Moderación | Oficial / Guild Master |
| `!reload [modulo]` | Admin | Propietario del bot |
| `!restart` | Admin | Propietario del bot |

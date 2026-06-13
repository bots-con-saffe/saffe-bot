# 📖 Comandos de Saffe-Bot

Guía detallada de todos los comandos del bot del gremio.

Todos los comandos funcionan de **dos formas**:
- Como **comando de texto** con el prefijo `!` (ejemplo: `!ping`)
- Como **slash command** escribiendo `/` (ejemplo: `/ping`)

> **Nota sobre permisos:** muchos comandos están restringidos por rol. En esta guía se indica quién puede usar cada uno:
> - 🟢 **Todos** — cualquier miembro
> - 🟡 **Creador de Contenido** + Staff
> - 🔵 **Oficial / Guild Master** (Staff)
> - 🔴 **Administrador** del servidor de Discord
>
> Varios comandos **solo funcionan dentro del hilo** de una actividad (el hilo que crea `/ping`). Se indica con 🧵.

---

## 📋 Índice

1. [Actividades y Plantillas (Pings)](#-actividades-y-plantillas-pings)
2. [Economía / Silver](#-economía--silver)
3. [Splits (Reparto de botín)](#-splits-reparto-de-botín)
4. [Multas](#-multas)
5. [Asistencias y Reportes](#-asistencias-y-reportes)
6. [Casino](#-casino)
7. [Moderación](#-moderación)
8. [Roles y Bienvenida](#-roles-y-bienvenida)
9. [Canales de Voz Temporales](#-canales-de-voz-temporales)
10. [Administración del Bot](#-administración-del-bot)

---

## ⚔️ Actividades y Plantillas (Pings)

El flujo típico es: creas **plantillas** (composiciones de roles), lanzas un **ping** que abre un hilo de inscripción, la gente se anota, y al final repartes con `/split` o cierras con `/end`.

### `/crear_plantilla` 🔵
Crea o actualiza una composición de roles reutilizable.
- **nombre**: nombre de la plantilla (ej: `dungeon`).
- **puestos**: los puestos separados por comas (ej: `Tanque, Healer, Dps, Dps`).
- Si la plantilla ya existe, **se sobrescribe** con los nuevos puestos.

### `/borrar_plantilla` 🔵
Elimina una plantilla guardada. Tiene autocompletado con las plantillas existentes.
- **nombre**: la plantilla a borrar.

### `/plantillas` 🟢
Lista todas las composiciones disponibles con sus puestos.

### `/ping` 🟡
Lanza una actividad: publica un embed con la lista de puestos, menciona al rol y **crea un hilo de inscripción**.
- **tipo**: la plantilla a usar (con autocompletado).
- **nombre_contenido**: nombre descriptivo (ej: `Ava 8.1`, `Dungeon T6`). Si contiene la palabra *"ava"*, la actividad cuenta como **doble asistencia** automáticamente.
- **fecha**: hora y día (ej: `Hoy 21:00`).
- **lugar**: mapa o zona (ej: `BZ Mists`).
- **rol** *(opcional)*: rol a mencionar. Si no se indica, se usa `@here`.
- **link_build** *(opcional)*: enlace o canal con las builds requeridas.

**Cómo se anota la gente:** dentro del hilo, cada quien escribe el **número** del puesto para anotarse (ej: `3`) o **`-número`** para salirse (ej: `-3`). El embed se actualiza solo. Si alguien se desanota, se le avisa al creador del ping.

### `/editar_actividad` 🔵 🧵
Modifica el lugar o la fecha de una actividad en curso.
- **lugar** *(opcional)*: nuevo mapa/zona.
- **fecha** *(opcional)*: nueva hora/día.

### `/start` 🟡 🧵
Avisa con una mención a **todos los anotados** que es hora de conectarse.

### `/end` 🟡 🧵
Cierra definitivamente la actividad **sin repartir silver**. Marca el embed como completado y archiva el hilo.

### `/anotar` 🟡 🧵
Anota manualmente a un miembro en una posición.
- **usuario**: el miembro a anotar.
- **numero**: número de la posición.

### `/desanotar` 🟡 🧵
Libera manualmente una posición (la deja vacía).
- **numero**: número de la posición a vaciar.

### `/agregar_cupos` 🔵 🧵
Añade ranuras extra de participantes a la actividad en curso.
- **cantidad**: cuántos cupos nuevos abrir (ej: `5`).
- **nombre** *(opcional)*: nombre para los cupos nuevos (ej: `Healer`). Si no lo indicas, los cupos toman el nombre de la plantilla.

---

## 💰 Economía / Silver

El sistema lleva un **balance** de silver por miembro (lo que el gremio le debe). Las cantidades aceptan abreviaturas: `500k` = 500.000 y `1.5m` = 1.500.000.

### `/balance` 🟢
Consulta el silver acumulado. Por defecto muestra el tuyo. Para ver el de otro miembro hace falta ser 🔵 Staff. Si tienes multas pendientes, muestra el balance bruto, las multas y el balance real.
- **usuario** *(opcional)*: miembro a consultar.

### `/balance_total_gremio` 🔵
Reporte de toda la deuda pendiente del gremio: cuánto silver se le debe a cada quien, ordenado de mayor a menor. Marca con ✅/❌ quién sigue en el servidor y quién se salió (útil para `/expropiar`).

### `/historial` 🟢
Muestra las últimas 10 transacciones de silver. Para ver el de otro hace falta ser 🔵 Staff.
- **usuario** *(opcional)*: miembro a consultar.

### `/pay` 🔵
Salda (paga) toda la deuda pendiente de un miembro, dejando su balance en 0. **Se bloquea si el miembro tiene multas pendientes.**
- **usuario**: el miembro a pagar.

### `/addbalance` 🔵
Suma silver al balance de un miembro manualmente.
- **usuario**, **cantidad**, **motivo** *(opcional)*.

### `/removebalance` 🔵
Resta silver del balance de un miembro (registra la transacción).
- **usuario**, **cantidad**, **motivo**.

### `/discount` 🔵
Aplica un descuento/multa manual rápido al balance.
- **usuario**, **cantidad**, **motivo** *(opcional)*.

### `/remove_balance` 🔵
Resetea el balance de un miembro a 0 **sin registrar transacción**. Se bloquea si tiene multas pendientes.
- **usuario**: el miembro.

### `/expropiar` 🔵
Quita **todo** el balance de un miembro. Funciona aunque ya **haya salido del servidor** (se puede buscar por nombre, no solo por mención).
- **usuario**: mención, ID o nombre del miembro.
- **motivo**: razón de la expropiación.

### `/wipe_silver` 🔴
⚠️ Borra **todos** los balances de silver del servidor. Acción destructiva.

### `/wipe_asistencias` 🔴
⚠️ Borra **todos** los registros de asistencia del servidor. Acción destructiva.

---

## 🪙 Splits (Reparto de botín)

Los splits reparten el silver de una actividad entre los anotados, registran su asistencia y (según el comando) cierran o no la actividad. Se usan **dentro del hilo**.

El cálculo descuenta primero el costo del mapa (de las bolsas), aplica el descuento por venta rápida al loot y luego el tax del gremio. El resto se reparte en partes iguales.

### `/split` 🟡 🧵
Reparte el silver, registra asistencia y **cierra y archiva** la actividad.
- **bolsas**: silver en bolsas (ej: `20m`).
- **loot**: estimado del loot (ej: `5m`).
- **costo_mapa** *(opcional, def. 0)*: costo del mapa.
- **tax_porcentaje** *(opcional, def. 15)*: % de tax del gremio sobre el loot.
- **venta_rapida** *(opcional, def. 0)*: % de descuento aplicado al loot por venta rápida.
- **excluir** *(opcional)*: miembro a excluir del reparto.

> **Aprobación:** si lo lanza un **Creador de Contenido** (sin rango de Oficial/GM), el reparto **no se ejecuta de inmediato**: se publica una solicitud etiquetando a **@Oficial** con botones *Aprobar/Rechazar*. El silver solo se reparte cuando un Oficial o GM **aprueba**. Si lo lanza un Oficial/GM, se ejecuta directo.

### `/split_medio` 🟡 🧵
Igual que `/split` pero **NO cierra** la actividad: reparte y registra asistencia, pero el hilo queda abierto para poder modificar la lista y volver a repartir. Mismos parámetros que `/split`. También requiere **aprobación de un Oficial** si lo lanza un Creador de Contenido.

### `/progremio` 🔵 🧵
Registra la asistencia **sin repartir silver** y cierra el hilo. Marca la actividad como **doble asistencia**.
- **excluir** *(opcional)*: miembro a excluir del registro.

### `/deshacer_split` 🔵 🧵
Revierte el **último** split del hilo:
- **Devuelve** el silver que se había repartido (funciona aunque alguien haya salido del servidor).
- **Borra** las asistencias generadas por ese split.
- Si el split había cerrado la actividad, **la reabre** (restaura la lista de inscripción y desarchiva el hilo) para que puedas volver a repartir.

> Requiere la tabla `splits_historial` en la base de datos.

---

## ⚠️ Multas

Las multas son deudas que se descuentan del balance y **bloquean los pagos** (`/pay`) hasta resolverse.

### `/multa` 🔵
Aplica una multa pendiente a un miembro.
- **usuario**, **cantidad**, **motivo**.

### `/ver_multas` 🟢
Muestra las multas pendientes de un miembro (con su ID). Para ver las de otro hace falta ser 🔵 Staff.
- **usuario** *(opcional)*.

### `/saldar_multa` 🟢
Paga **una** de tus multas descontándola de tu balance (menú desplegable para elegir cuál). Cualquiera puede saldar las suyas; solo el 🔵 Staff puede saldar las de **otro** miembro.
- **usuario** *(opcional)*: el miembro (por defecto, tú mismo).

### `/saldar_todas_multas` 🟢
Usa tu balance para pagar **todas** tus multas (hasta donde alcance el saldo). Cualquiera para las suyas; solo el 🔵 Staff para las de otro.
- **usuario** *(opcional)*: el miembro (por defecto, tú mismo).

### `/quitar_multa` 🔵
Cancela una multa por su **ID** (visible en `/ver_multas`) sin descontar nada.
- **multa_id**: el ID de la multa.

---

## 📊 Asistencias y Reportes

La asistencia se mide en **puntos**: cada participación vale 1, salvo las actividades de doble asistencia (Ava o `/progremio`) que valen 2.

### `/asistencias` 🟢
Muestra el historial de las últimas 15 actividades de un miembro. Para ver el de otro hace falta ser 🔵 Staff.
- **usuario** *(opcional)*.

### `/borrar_asistencia` 🔵
Elimina una asistencia específica de un miembro (con autocompletado de sus actividades).
- **usuario**, **indice**.

### `/top` 🔵
Ranking de los miembros con más puntos de asistencia en el periodo.
- **periodo** *(opcional, def. `semana`)*: `semana`, `bisemanal` o `total`.

### `/lista_asistencias_total` 🔵
Muestra la actividad de **todos** los miembros con roles de gremio, incluyendo los que tienen 0 puntos (marcados como inactivos). Útil para limpiezas.
- **periodo** *(opcional, def. `semana`)*.

### `/asistencias_rango` 🔵
Puntos acumulados entre **dos fechas exactas**.
- **desde**, **hasta**: formato `DD/MM/YYYY` (ej: `01/05/2026`).

### `/ultima_asistencia_gremio` 🔵
Muestra cuándo fue la **última** asistencia de cada miembro del gremio, y quién no tiene ninguna registrada.

### `/sorteo` 🔵
Elige un **ganador aleatorio** ponderado por tickets de asistencia (mientras más asistencias, más probabilidad).

### `/reporte` 🔵
Resumen del periodo: actividades realizadas, participantes únicos, silver repartido y desglose por tipo de actividad.
- **periodo** *(opcional, def. `semana`)*: `semana` o `bisemanal`.

---

## 🎰 Casino

Mini-juegos de apuestas contra el **banco del gremio**. La apuesta máxima general es **600k**. El banco debe tener fondos suficientes para cubrir el doble de la apuesta.

> **Rol "Donador Certificado":** quien pierde más de **5m** en un día recibe este rol y queda limitado a apostar como máximo **1.5m al día** hasta que expire.

### `/ruleta` 🟢
🔫 Ruleta rusa **entre jugadores** (no contra la casa). Se paga un asiento y el bote va para el sobreviviente.
- **apuesta**: precio del asiento (ej: `500k`).

### `/dados` 🟢
🎲 Tiras un dado contra la casa; el número más alto gana.
- **apuesta**: plata a apostar (máx 600k).

### `/blackjack` 🃏
Blackjack contra la casa, intentando llegar a 21. Incluye botones de pedir/plantarse/doblar.
- **apuesta**: plata a apostar (máx 600k).

### `/under_over` 🟢
🎲 Se lanzan **2 dados** y apuestas (con botones) a cómo será la suma:
- ⬇️ **Bajo (2–6)** → paga **x1** (doblas la apuesta).
- 7️⃣ **Siete exacto** → paga **x2**.
- ⬆️ **Alto (8–12)** → paga **x1** (doblas la apuesta).
- Si sale **7** y elegiste Bajo o Alto, **pierdes**.
- **apuesta**: plata a apostar (máx 600k). No se cobra nada hasta que pulsas un botón.

### `/banco_balance` 🔵
Muestra el balance del banco del gremio.

### `/banco_depositar` 🔵
Añade silver al banco del gremio.
- **cantidad**: a depositar (ej: `5m`).

### `/banco_retirar` 🔵
Retira silver del banco (para registrar ganancias).
- **cantidad**, **motivo** *(opcional)*.

### `/quitar_donador` 🔵
Quita manualmente el rol **Donador Certificado** a un miembro.
- **usuario**: el miembro.

### `/top_sorteo` 🔵
Muestra el **top 10** de candidatos al próximo sorteo (más activos de los últimos 7 días; los Oficiales quedan excluidos).

### `/sorteo_participacion` 🔵
🎰 Sorteo épico animado entre los 10 más activos de los últimos 7 días.

---

## 🛡️ Moderación

### `/clear` 🔵
Borra los últimos N mensajes del canal (respeta los anclados).
- **cantidad** *(opcional, def. 5)*.

### `/callout` 🟡 🧵
**Cancela** la actividad del hilo (marca el embed como cancelada y archiva).
- **motivo**: razón de la cancelación.
- **asistencia** *(opcional, def. `false`)*: si es `true`, registra la asistencia de los anotados antes de cancelar.

### `/kick_gremio` 🔵
Quita **todos** los roles de un miembro, le envía un MD y lo **expulsa** del Discord. Pensado para limpieza de inactivos.
- **usuario**, **motivo** *(opcional)*.

### `/kick` 🔵
Expulsa a un miembro (con botón de confirmación).
- **member**, **razon** *(opcional)*.

### `/timeout` 🔵
Silencia (timeout) a un miembro durante N minutos (con confirmación). No funciona sobre roles protegidos (Oficial/Guild Master).
- **member**, **minutos**, **razon** *(opcional)*.

---

## 👥 Roles y Bienvenida

### `/rol` 🔵
Asigna un **paquete de roles** de golpe a un nuevo integrante y le quita el rol Scout.
- **paquete**: `miembro` (Miembro, PvE Content, PvP Content) o `miembroava` (lo anterior + Ava Core).
- **usuario**: el miembro a rankear.

### `/test_scout` 🟢
Prueba el sistema de bienvenida: simula tu entrada para verificar que el rol **Scout** y el mensaje de ingreso funcionan.

> **Automático (sin comando):** al entrar un miembro nuevo, el bot le asigna el rol **Scout** y publica un saludo en el canal de *ingresos*.

---

## 🔊 Canales de Voz Temporales

El bot crea automáticamente una sala de voz propia cuando entras a un canal "Crear…" de su categoría. El **líder** de la sala (quien la creó) puede gestionarla con estos comandos. El liderazgo se transfiere solo si el dueño se va, y la sala se borra cuando queda vacía.

### `/name` 🟢 *(solo el líder de la sala)*
Cambia el nombre de tu sala.
- **nuevo_nombre**.

### `/limite` 🟢 *(solo el líder)*
Establece el límite de usuarios de la sala.
- **num**: máximo de usuarios (`0` = sin límite).

### `/lock` 🟢 *(solo el líder)*
Bloquea tu sala (nadie nuevo puede entrar).

### `/unlock` 🟢 *(solo el líder)*
Vuelve a abrir tu sala.

---

## 🔧 Administración del Bot

Comandos solo de texto (`!`), reservados al 🔴 **Administrador** del servidor.

### `!reload [modulo]`
Recarga los cogs sin reiniciar el bot. Sin argumento recarga **todos**; con un nombre recarga solo ese (ej: `!reload pings`).

### `!sync [guild_id]`
Sincroniza los slash commands. **Recomendado:** `!sync <guild_id>` para tu servidor (instantáneo). Evita `!sync` sin argumento (sincroniza global y puede **duplicar** los comandos).

### `!restart`
Reinicia el proceso del bot por completo.

### `!limpiar_comandos`
Soluciona los **comandos duplicados**: purga el registro global de Discord y deja los comandos registrados solo a nivel de este servidor. Úsalo una vez si ves comandos repetidos en la lista.

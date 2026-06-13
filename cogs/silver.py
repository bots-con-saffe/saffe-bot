import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from db import get_db, get_balance_lock


async def _ajustar_balance_id(user_id: str, nombre: str, cantidad: int, tipo: str, motivo: str):
    """Ajusta el balance por ID de usuario. Funciona aunque el miembro ya no esté en el servidor."""
    async with get_balance_lock(user_id):
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('balance, usuario_nombre').eq('usuario_id', user_id).execute()
        )
        balance_actual = result.data[0]['balance'] if result.data else 0
        nombre_final   = nombre or (result.data[0]['usuario_nombre'] if result.data else 'Desconocido')
        nuevo_balance  = balance_actual + cantidad

        await asyncio.to_thread(
            lambda: get_db().table('balances')
                .upsert({'usuario_id': user_id, 'usuario_nombre': nombre_final, 'balance': nuevo_balance}, on_conflict='usuario_id')
                .execute()
        )
        await asyncio.to_thread(
            lambda: get_db().table('transacciones')
                .insert({'usuario_id': user_id, 'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo})
                .execute()
        )


async def _actualizar_balance(member: discord.Member, cantidad: int, tipo: str, motivo: str):
    await _ajustar_balance_id(str(member.id), member.display_name, cantidad, tipo, motivo)


class Silver(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def formatear(self, cantidad: int) -> str:
        return f"{cantidad:,}"

    def convertir_unidad(self, entrada: str) -> int:
        """Convierte '20m', '500k', '1.5m' a entero."""
        if isinstance(entrada, int):
            return entrada
        texto = str(entrada).lower().replace(" ", "")
        try:
            if texto.endswith('k'):
                return int(float(texto[:-1].replace(",", ".")) * 1_000)
            if texto.endswith('m'):
                return int(float(texto[:-1].replace(",", ".")) * 1_000_000)
            return int(float(texto.replace(",", ".")))
        except:
            return 0

    # --- BALANCE ---

    @commands.hybrid_command(name="balance", description="Consulta el silver acumulado")
    @app_commands.describe(usuario="Miembro a consultar (solo Oficial/GM para ver el de otro)")
    async def balance(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        if usuario and usuario != ctx.author:
            if not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden consultar el balance de otros.", delete_after=5)
            target = usuario
        else:
            target = ctx.author

        result, multas_result = await asyncio.gather(
            asyncio.to_thread(
                lambda: get_db().table('balances').select('balance').eq('usuario_id', str(target.id)).execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('multas').select('cantidad').eq('usuario_id', str(target.id)).eq('pagada', False).execute()
            )
        )
        saldo        = result.data[0]['balance'] if result.data else 0
        total_multas = sum(m['cantidad'] for m in multas_result.data) if multas_result.data else 0
        balance_real = saldo - total_multas

        embed = discord.Embed(title=f"💰 Balance de {target.display_name}", color=discord.Color.gold())
        if total_multas > 0:
            embed.add_field(name="💰 Balance Bruto",        value=f"**{self.formatear(saldo)}** silver",         inline=True)
            embed.add_field(name="⚠️ Multas Pendientes",   value=f"**-{self.formatear(total_multas)}** silver",  inline=True)
            embed.add_field(name="📊 Balance Real",         value=f"**{self.formatear(balance_real)}** silver",   inline=True)
        else:
            embed.description = f"**{self.formatear(saldo)}** silver"
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance_total_gremio", description="Suma total de silver que el gremio debe pagar a los miembros")
    @commands.has_any_role("Oficial", "Guild Master")
    async def balance_total_gremio(self, ctx):
        await ctx.defer()
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('usuario_id, usuario_nombre, balance')
                .neq('usuario_id', 'BANCO_GREMIO').execute()
        )
        if not result.data:
            return await ctx.send("📊 La base de datos de balances está vacía.")

        deuda_total = 0
        detalles = []
        for row in result.data:
            saldo = row.get('balance', 0)
            if saldo > 0:
                deuda_total += saldo
                detalles.append((row.get('usuario_id', ''), row.get('usuario_nombre', 'Desconocido'), saldo))

        if deuda_total == 0:
            return await ctx.send(embed=discord.Embed(
                title="📈 Balance General del Gremio",
                description="✅ **¡El gremio está al día!** No se le debe silver a nadie.",
                color=discord.Color.green()
            ))

        detalles.sort(key=lambda x: -x[2])

        lineas = []
        for uid, nombre, saldo in detalles:
            try:
                en_server = ctx.guild.get_member(int(uid)) is not None
            except (ValueError, TypeError):
                en_server = False
            if en_server:
                lineas.append(f"✅ **{nombre}**: {self.formatear(saldo)} silver")
            else:
                lineas.append(f"❌ `{nombre}`: {self.formatear(saldo)} silver")

        embed = discord.Embed(
            title="📊 Reporte de Deuda Pendiente del Gremio",
            description=(
                f"💰 **Total a Pagar:** {self.formatear(deuda_total)} silver\n"
                f"👥 **Jugadores con saldo:** {len(detalles)}\n"
                f"✅ En servidor  •  ❌ Salió del DC *(copia el nombre para `/expropiar`)*"
            ),
            color=discord.Color.red()
        )

        chunk, num = "", 1
        for linea in lineas:
            if len(chunk) + len(linea) + 1 > 1000:
                embed.add_field(name=f"📋 Desglose ({num})", value=chunk.strip(), inline=False)
                chunk, num = "", num + 1
            chunk += linea + "\n"
        if chunk:
            embed.add_field(name=f"📋 Desglose ({num})", value=chunk.strip(), inline=False)

        embed.set_footer(text="Usa /pay para saldar • /expropiar <nombre> para quien salió del DC")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="historial", description="Muestra las últimas transacciones de silver")
    @app_commands.describe(usuario="Miembro a consultar (solo Oficial/GM para ver el de otro)")
    async def historial(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        if usuario and usuario != ctx.author:
            if not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden ver el historial de otros.", delete_after=5)
            target = usuario
        else:
            target = ctx.author

        result = await asyncio.to_thread(
            lambda: get_db().table('transacciones')
                .select('tipo, cantidad, motivo, fecha')
                .eq('usuario_id', str(target.id))
                .order('fecha', desc=True)
                .limit(10)
                .execute()
        )
        if not result.data:
            return await ctx.send(f"No hay transacciones registradas para **{target.display_name}**.", delete_after=7)

        embed = discord.Embed(title=f"📋 Historial de {target.display_name}", color=discord.Color.blurple())
        for tx in result.data:
            signo = "+" if tx['cantidad'] > 0 else ""
            fecha = tx['fecha'][:10]
            embed.add_field(
                name=f"{signo}{self.formatear(tx['cantidad'])} silver — {fecha}",
                value=f"`{tx['tipo']}` · {tx['motivo'] or 'Sin motivo'}",
                inline=False
            )
        await ctx.send(embed=embed)

    # --- SPLIT ---

    @commands.hybrid_command(name="split", description="Reparte silver, registra asistencia y cierra la actividad")
    @app_commands.describe(
        bolsas="Silver en bolsas (Ej: 20m, 500k)",
        loot="Estimado del loot (Ej: 5m)",
        costo_mapa="Costo del mapa (Ej: 500k)",
        tax_porcentaje="% de tax del gremio sobre el loot (Ej: 15)",
        venta_rapida="% de descuento aplicado al loot por venta rápida",
        excluir="Miembro a excluir del reparto"
    )
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def split(self, ctx, bolsas: str, loot: str, costo_mapa: str = "0", tax_porcentaje: int = 15, venta_rapida: int = 0, excluir: discord.Member = None):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo activo.", delete_after=5)
        await ctx.defer()

        params = dict(bolsas=bolsas, loot=loot, costo_mapa=costo_mapa,
                      tax_porcentaje=tax_porcentaje, venta_rapida=venta_rapida, excluir=excluir)

        # Creador de Contenido (sin rango de Staff): el split debe aprobarlo un Oficial
        if not self._es_staff(ctx.author):
            return await self._solicitar_aprobacion_split(ctx, params, cerrar=True)

        ok, payload = await self._realizar_split(ctx.channel, ctx.guild, cerrar=True, **params)
        if not ok:
            return await ctx.send(payload)
        await ctx.send(embed=payload)
        await ctx.channel.edit(locked=True, archived=True)

    def _es_staff(self, member) -> bool:
        return any(r.name in ("Oficial", "Guild Master") for r in member.roles)

    async def _realizar_split(self, channel, guild, *, cerrar, bolsas, loot, costo_mapa="0",
                              tax_porcentaje=15, venta_rapida=0, excluir=None):
        """Ejecuta el reparto completo. Devuelve (True, embed) en éxito o (False, mensaje_error)."""
        hilo_id = str(channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return False, "❌ No hay una actividad activa registrada en este hilo."

        registro = result.data[0]
        ids_validos = [uid for uid in registro['participantes'].values() if uid is not None]

        participantes = []
        for uid in ids_validos:
            if excluir and str(excluir.id) == uid:
                continue
            m = guild.get_member(int(uid))
            if m and not m.bot:
                participantes.append(m)

        if not participantes:
            return False, "❌ No hay miembros anotados para efectuar el reparto."

        v_bolsas = self.convertir_unidad(bolsas)
        v_loot = self.convertir_unidad(loot)
        v_costo_mapa = self.convertir_unidad(costo_mapa)

        loot_inicial = int(v_loot * (1 - venta_rapida / 100))
        mapa_pendiente = v_costo_mapa

        cobrado_bolsas = min(v_bolsas, mapa_pendiente)
        bolsas_restantes = v_bolsas - cobrado_bolsas
        mapa_pendiente -= cobrado_bolsas

        cobrado_loot = min(loot_inicial, mapa_pendiente)
        loot_restante = loot_inicial - cobrado_loot

        tax = int(loot_restante * (tax_porcentaje / 100))
        loot_final = loot_restante - tax

        total_neto = max(0, bolsas_restantes + loot_final)
        por_persona = total_neto // len(participantes)

        tipo_tx = "split" if cerrar else "split_medio"
        motivo = ("Split" if cerrar else "Split Parcial") + f": {channel.name}"

        lista_pagos = ""
        for p in participantes:
            await _actualizar_balance(p, por_persona, tipo_tx, motivo)
            lista_pagos += f"{p.mention}: **{self.formatear(por_persona)}**\n"

        # Registrar asistencias
        asistencias_data = [{
            'registro_actividad_id': registro['registro_actividad_id'],
            'usuario_id': str(p.id),
            'usuario_nombre': p.display_name
        } for p in participantes]
        await asyncio.to_thread(
            lambda: get_db().table('asistencias').insert(asistencias_data).execute()
        )

        # Guardar snapshot para poder revertir el split (/deshacer_split)
        pagos_split = {str(p.id): por_persona for p in participantes}
        await asyncio.to_thread(
            lambda: get_db().table('splits_historial').insert({
                'hilo_id': hilo_id,
                'registro_actividad_id': registro['registro_actividad_id'],
                'tipo_split': tipo_tx,
                'pagos': pagos_split,
                'cerro_actividad': cerrar,
                'registro_snapshot': registro
            }).execute()
        )

        if cerrar:
            pings_cog = self.bot.get_cog("PingsAlbion")
            if pings_cog:
                await pings_cog.actualizar_mensaje(channel, registro, estado="finalizada")
            await asyncio.to_thread(
                lambda: get_db().table('registros_activos').delete().eq('hilo_id', hilo_id).execute()
            )

        if cerrar:
            embed = discord.Embed(title="💰 Reparto Avanzado y Asistencia Registrada", color=discord.Color.green())
        else:
            embed = discord.Embed(
                title="⏳ Reparto Parcial Completado",
                description="La actividad **SIGUE ABIERTA**. Puedes modificar la plantilla y hacer otro split.",
                color=discord.Color.orange()
            )
        resumen = (
            f"**Bolsas iniciales:** {self.formatear(v_bolsas)}\n"
            f"**Loot neto recaudado:** {self.formatear(loot_inicial)}\n"
            f"**Costo de mapa:** -{self.formatear(v_costo_mapa)} *(cobrado de las bolsas primero)*\n"
            f"**Tax gremio ({tax_porcentaje}% del loot):** -{self.formatear(tax)}\n"
            f"**Total neto a repartir:** {self.formatear(total_neto)}"
        )
        embed.add_field(name="Resumen de Operación", value=resumen, inline=False)
        embed.add_field(name="👥 Distribución Detallada", value=lista_pagos, inline=False)
        embed.set_footer(text="Contenido completado. Hilo archivado." if cerrar
                         else "Usa /desanotar para liberar puestos antes del próximo split.")
        return True, embed

    async def _solicitar_aprobacion_split(self, ctx, params, cerrar):
        rol_oficial = discord.utils.get(ctx.guild.roles, name="Oficial")
        mencion = rol_oficial.mention if rol_oficial else "**Oficiales**"
        tipo_txt = "Split (cierra la actividad)" if cerrar else "Split parcial (no cierra)"

        resumen = (
            f"📦 **Bolsas:** {params['bolsas']}\n"
            f"💎 **Loot:** {params['loot']}\n"
            f"🗺️ **Costo mapa:** {params['costo_mapa']}\n"
            f"🏦 **Tax:** {params['tax_porcentaje']}%\n"
            f"⚡ **Venta rápida:** {params['venta_rapida']}%"
        )
        if params['excluir']:
            resumen += f"\n🚫 **Excluye a:** {params['excluir'].mention}"

        embed = discord.Embed(
            title="⏳ Split pendiente de aprobación",
            description=(
                f"{ctx.author.mention} (Creador de Contenido) solicita un **{tipo_txt}**.\n\n"
                f"{resumen}\n\n"
                "Un **Oficial** o **Guild Master** debe aprobarlo. El silver **no se reparte** hasta entonces."
            ),
            color=discord.Color.orange()
        )
        view = AprobacionSplitView(self, solicitante=ctx.author, channel=ctx.channel,
                                   guild=ctx.guild, params=params, cerrar=cerrar)
        msg = await ctx.send(
            content=f"🔔 {mencion} — revisión de split solicitada por **{ctx.author.display_name}**",
            embed=embed, view=view
        )
        view.msg = msg

    @commands.hybrid_command(name="progremio", description="Registra asistencia de la actividad sin repartir silver y cierra el hilo")
    @app_commands.describe(excluir="Miembro a excluir del registro")
    @commands.has_any_role("Oficial", "Guild Master")
    async def progremio(self, ctx, excluir: discord.Member = None):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo activo.", delete_after=5)
        await ctx.defer()

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay una actividad activa registrada en este hilo.")

        registro = result.data[0]
        ids_validos = [uid for uid in registro['participantes'].values() if uid is not None]

        participantes = []
        for uid in ids_validos:
            if excluir and str(excluir.id) == uid:
                continue
            m = ctx.guild.get_member(int(uid))
            if m and not m.bot:
                participantes.append(m)

        if not participantes:
            return await ctx.send("❌ No hay miembros anotados en esta actividad.")

        # Marcar la actividad como doble asistencia
        await asyncio.to_thread(
            lambda: get_db().table('registros_actividad')
                .update({'multiplicador': 2})
                .eq('id', registro['registro_actividad_id'])
                .execute()
        )

        asistencias_data = [{
            'registro_actividad_id': registro['registro_actividad_id'],
            'usuario_id': str(p.id),
            'usuario_nombre': p.display_name
        } for p in participantes]
        await asyncio.to_thread(
            lambda: get_db().table('asistencias').insert(asistencias_data).execute()
        )

        pings_cog = self.bot.get_cog("PingsAlbion")
        if pings_cog:
            await pings_cog.actualizar_mensaje(ctx.channel, registro, estado="finalizada")

        await asyncio.to_thread(
            lambda: get_db().table('registros_activos').delete().eq('hilo_id', hilo_id).execute()
        )

        lista = "\n".join(p.mention for p in participantes)
        embed = discord.Embed(
            title="🛡️ Pro Gremio — Asistencia Registrada",
            color=discord.Color.blurple()
        )
        embed.add_field(name=f"👥 Participantes ({len(participantes)})", value=lista, inline=False)
        embed.set_footer(text="✨ Doble asistencia aplicada. Sin reparto de silver. Hilo archivado.")
        await ctx.send(embed=embed)
        await ctx.channel.edit(locked=True, archived=True)

    @commands.hybrid_command(name="split_medio", description="Reparte silver y registra asistencia SIN cerrar la actividad")
    @app_commands.describe(
        bolsas="Silver en bolsas (Ej: 20m, 500k)",
        loot="Estimado del loot (Ej: 5m)",
        costo_mapa="Costo del mapa (Ej: 500k)",
        tax_porcentaje="% de tax del gremio sobre el loot (Ej: 15)",
        venta_rapida="% de descuento aplicado al loot por venta rápida",
        excluir="Miembro a excluir del reparto"
    )
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def split_medio(self, ctx, bolsas: str, loot: str, costo_mapa: str = "0", tax_porcentaje: int = 15, venta_rapida: int = 0, excluir: discord.Member = None):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo activo.", delete_after=5)
        await ctx.defer()

        params = dict(bolsas=bolsas, loot=loot, costo_mapa=costo_mapa,
                      tax_porcentaje=tax_porcentaje, venta_rapida=venta_rapida, excluir=excluir)

        # Creador de Contenido (sin rango de Staff): el split debe aprobarlo un Oficial
        if not self._es_staff(ctx.author):
            return await self._solicitar_aprobacion_split(ctx, params, cerrar=False)

        ok, payload = await self._realizar_split(ctx.channel, ctx.guild, cerrar=False, **params)
        if not ok:
            return await ctx.send(payload)
        await ctx.send(embed=payload)

    @commands.hybrid_command(name="deshacer_split", description="Revierte el último split del hilo: devuelve el silver, borra asistencias y reabre la actividad")
    @commands.has_any_role("Oficial", "Guild Master")
    async def deshacer_split(self, ctx):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)
        await ctx.defer()

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('splits_historial').select('*')
                .eq('hilo_id', hilo_id).order('id', desc=True).limit(1).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay ningún split registrado en este hilo para revertir.")

        hist = result.data[0]
        pagos = hist.get('pagos') or {}
        registro_actividad_id = hist.get('registro_actividad_id')

        # 1. Devolver el silver repartido (funciona aunque el miembro haya salido)
        devuelto_total = 0
        for user_id, cantidad in pagos.items():
            cantidad = int(cantidad)
            if cantidad == 0:
                continue
            miembro = ctx.guild.get_member(int(user_id))
            nombre = miembro.display_name if miembro else None
            await _ajustar_balance_id(user_id, nombre, -cantidad, "deshacer_split", f"Reversa de split: {ctx.channel.name}")
            devuelto_total += cantidad

        # 2. Borrar las asistencias generadas por ese split
        if registro_actividad_id and pagos:
            await asyncio.to_thread(
                lambda: get_db().table('asistencias').delete()
                    .eq('registro_actividad_id', registro_actividad_id)
                    .in_('usuario_id', list(pagos.keys()))
                    .execute()
            )

        # 3. Reabrir la actividad si el split la había cerrado
        reabierta = False
        if hist.get('cerro_actividad'):
            snap = hist.get('registro_snapshot') or {}
            existe = await asyncio.to_thread(
                lambda: get_db().table('registros_activos').select('hilo_id').eq('hilo_id', hilo_id).execute()
            )
            if not existe.data and snap:
                nuevo_registro = {
                    'hilo_id': hilo_id,
                    'registro_actividad_id': snap.get('registro_actividad_id'),
                    'guild_id': snap.get('guild_id'),
                    'tipo': snap.get('tipo'),
                    'nombre_contenido': snap.get('nombre_contenido'),
                    'fecha_actividad': snap.get('fecha_actividad'),
                    'lugar': snap.get('lugar'),
                    'link_build': snap.get('link_build'),
                    'multiplicador': snap.get('multiplicador'),
                    'msg_id': snap.get('msg_id'),
                    'puestos_nombres': snap.get('puestos_nombres'),
                    'participantes': snap.get('participantes'),
                }
                await asyncio.to_thread(
                    lambda: get_db().table('registros_activos').insert(nuevo_registro).execute()
                )
                try:
                    await ctx.channel.edit(archived=False, locked=False)
                except Exception as e:
                    print(f"⚠️ No se pudo reabrir el hilo en deshacer_split: {e}")
                pings_cog = self.bot.get_cog("PingsAlbion")
                if pings_cog:
                    await pings_cog.actualizar_mensaje(ctx.channel, nuevo_registro, estado="abierta")
                reabierta = True

        # 4. Eliminar el registro de historial ya revertido
        await asyncio.to_thread(
            lambda: get_db().table('splits_historial').delete().eq('id', hist['id']).execute()
        )

        embed = discord.Embed(title="↩️ Split revertido", color=discord.Color.gold())
        embed.add_field(
            name="💸 Silver devuelto",
            value=f"**{self.formatear(devuelto_total)}** retirado de **{len(pagos)}** jugador(es)",
            inline=False
        )
        if reabierta:
            embed.add_field(
                name="🔓 Actividad reabierta",
                value="La inscripción volvió a abrirse. Ajusta la lista y vuelve a hacer el split.",
                inline=False
            )
        else:
            embed.set_footer(text="La actividad seguía abierta (split parcial). Vuelve a repartir cuando quieras.")
        await ctx.send(embed=embed)

    # --- GESTIÓN DE BALANCES ---

    @commands.hybrid_command(name="pay", description="Salda la deuda pendiente de un miembro")
    @commands.has_any_role("Oficial", "Guild Master")
    async def pay(self, ctx, usuario: discord.Member):
        balance_result, multas_result = await asyncio.gather(
            asyncio.to_thread(
                lambda: get_db().table('balances').select('balance').eq('usuario_id', str(usuario.id)).execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('multas').select('id, cantidad, motivo').eq('usuario_id', str(usuario.id)).eq('pagada', False).execute()
            )
        )
        if not balance_result.data or balance_result.data[0]['balance'] <= 0:
            return await ctx.send("❌ Este miembro no tiene balance pendiente.")
        if multas_result.data:
            total_multas = sum(m['cantidad'] for m in multas_result.data)
            lineas = [f"• `#{m['id']}` {self.formatear(m['cantidad'])} silver — {m['motivo']}" for m in multas_result.data]
            embed = discord.Embed(
                title="⛔ Pago bloqueado — Multas pendientes",
                description=f"{usuario.mention} tiene **{len(multas_result.data)} multa(s)** por un total de **{self.formatear(total_multas)} silver**.\nResuélvelas antes de pagar el balance.\n\n" + "\n".join(lineas),
                color=discord.Color.red()
            )
            embed.set_footer(text="Usa /quitar_multa <id> para cancelar una multa")
            return await ctx.send(embed=embed)
        deuda = balance_result.data[0]['balance']
        await _actualizar_balance(usuario, -deuda, "pago", "Pago total de deuda")
        await ctx.send(f"✅ Pagados **{self.formatear(deuda)}** silver a {usuario.mention}.")

    @commands.hybrid_command(name="discount", description="Aplica una multa o descuento manual al balance de un miembro")
    @app_commands.describe(usuario="El miembro", cantidad="Cantidad a descontar (Ej: 500k, 1m)", motivo="Razón del descuento")
    @commands.has_any_role("Oficial", "Guild Master")
    async def discount(self, ctx, usuario: discord.Member, cantidad: str, *, motivo: str = "Descuento"):
        valor = self.convertir_unidad(cantidad)
        await _actualizar_balance(usuario, -valor, "descuento", motivo)
        await ctx.send(f"📉 Descontados **{self.formatear(valor)}** a {usuario.mention}. Motivo: *{motivo}*")

    @commands.hybrid_command(name="addbalance", description="Suma silver al balance de un miembro manualmente")
    @app_commands.describe(usuario="El miembro", cantidad="Cantidad a sumar (Ej: 500k, 1m)", motivo="Razón del ajuste")
    @commands.has_any_role("Oficial", "Guild Master")
    async def addbalance(self, ctx, usuario: discord.Member, cantidad: str, *, motivo: str = "Ajuste manual"):
        valor = self.convertir_unidad(cantidad)
        await _actualizar_balance(usuario, valor, "ajuste_manual", motivo)
        await ctx.send(f"✅ Sumados **{self.formatear(valor)}** silver a {usuario.mention}.")

    @commands.hybrid_command(name="removebalance", description="Resta silver del balance de un miembro manualmente")
    @app_commands.describe(usuario="El miembro", cantidad="Cantidad a restar (Ej: 500k, 1m)", motivo="Razón del ajuste")
    @commands.has_any_role("Oficial", "Guild Master")
    async def removebalance(self, ctx, usuario: discord.Member, cantidad: str, *, motivo: str):
        valor = self.convertir_unidad(cantidad)
        await _actualizar_balance(usuario, -valor, "ajuste_manual", motivo)
        await ctx.send(f"✅ Restados **{self.formatear(valor)}** silver a {usuario.mention}. Motivo: *{motivo}*")

    @commands.hybrid_command(name="expropiar", description="Quita TODO el balance de un miembro (funciona aunque haya salido del servidor)")
    @app_commands.describe(usuario="Nombre del miembro o mención", motivo="Razón de la expropiación")
    @commands.has_any_role("Oficial", "Guild Master")
    async def expropiar(self, ctx, usuario: str, *, motivo: str):
        # Intentar resolver como Member (mención o ID numérico)
        target_id     = None
        target_nombre = None
        saldo         = 0

        uid_str = usuario.strip('<@!> ')
        if uid_str.isdigit():
            member = ctx.guild.get_member(int(uid_str))
            if member:
                target_id     = str(member.id)
                target_nombre = member.display_name

        if target_id:
            result = await asyncio.to_thread(
                lambda: get_db().table('balances').select('balance').eq('usuario_id', target_id).execute()
            )
            saldo = result.data[0]['balance'] if result.data else 0
        else:
            # Buscar por nombre en la tabla balances
            result = await asyncio.to_thread(
                lambda: get_db().table('balances').select('usuario_id, usuario_nombre, balance')
                    .ilike('usuario_nombre', f'%{usuario}%')
                    .neq('usuario_id', 'BANCO_GREMIO').execute()
            )
            if not result.data:
                return await ctx.send(f"❌ No se encontró ningún usuario con el nombre **{usuario}** en la base de datos.", delete_after=8)
            if len(result.data) > 1:
                lineas = [f"• **{r['usuario_nombre']}** — {self.formatear(r['balance'])} silver" for r in result.data[:10]]
                return await ctx.send(embed=discord.Embed(
                    title="⚠️ Múltiples coincidencias — sé más específico",
                    description="\n".join(lineas),
                    color=discord.Color.orange()
                ))
            row           = result.data[0]
            target_id     = row['usuario_id']
            target_nombre = row['usuario_nombre']
            saldo         = row['balance']

        if saldo <= 0:
            return await ctx.send(f"❌ **{target_nombre}** no tiene silver para expropiar.", delete_after=5)

        async with get_balance_lock(target_id):
            await asyncio.to_thread(
                lambda: get_db().table('balances').update({'balance': 0}).eq('usuario_id', target_id).execute()
            )
            await asyncio.to_thread(
                lambda: get_db().table('transacciones').insert({
                    'usuario_id': target_id, 'tipo': 'expropiacion', 'cantidad': -saldo, 'motivo': motivo
                }).execute()
            )

        embed = discord.Embed(title="⚖️ Expropiación Total", color=discord.Color.dark_red())
        embed.add_field(name="Miembro",  value=target_nombre,                         inline=True)
        embed.add_field(name="Cantidad", value=f"**{self.formatear(saldo)}** silver", inline=True)
        embed.add_field(name="Motivo",   value=motivo,                                inline=False)
        embed.set_footer(text=f"Ejecutado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # --- MULTAS ---

    @commands.hybrid_command(name="multa", description="Aplica una multa pendiente a un miembro")
    @app_commands.describe(usuario="El miembro", cantidad="Cantidad de la multa (Ej: 500k, 1m)", motivo="Razón de la multa")
    @commands.has_any_role("Oficial", "Guild Master")
    async def multa(self, ctx, usuario: discord.Member, cantidad: str, *, motivo: str):
        valor = self.convertir_unidad(cantidad)
        if valor <= 0:
            return await ctx.send("❌ Cantidad inválida.", delete_after=5)
        await asyncio.to_thread(
            lambda: get_db().table('multas').insert({
                'usuario_id':     str(usuario.id),
                'usuario_nombre': usuario.display_name,
                'cantidad':       valor,
                'motivo':         motivo
            }).execute()
        )
        embed = discord.Embed(title="⚠️ Multa Registrada", color=discord.Color.orange())
        embed.add_field(name="Miembro",  value=usuario.mention,                        inline=True)
        embed.add_field(name="Cantidad", value=f"**{self.formatear(valor)}** silver",  inline=True)
        embed.add_field(name="Motivo",   value=motivo,                                 inline=False)
        embed.set_footer(text=f"Aplicada por {ctx.author.display_name} • Usa /ver_multas para ver el detalle")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ver_multas", description="Muestra las multas pendientes de un miembro")
    @app_commands.describe(usuario="Miembro a consultar (solo Oficial/GM para ver el de otro)")
    async def ver_multas(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)
        if usuario and usuario != ctx.author:
            if not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden ver las multas de otros.", delete_after=5)
            target = usuario
        else:
            target = ctx.author

        result = await asyncio.to_thread(
            lambda: get_db().table('multas').select('id, cantidad, motivo, fecha')
                .eq('usuario_id', str(target.id)).eq('pagada', False)
                .order('fecha', desc=False).execute()
        )
        if not result.data:
            return await ctx.send(embed=discord.Embed(
                title=f"✅ Sin multas — {target.display_name}",
                description="No tiene multas pendientes.",
                color=discord.Color.green()
            ))

        total = sum(m['cantidad'] for m in result.data)
        lineas = [
            f"`#{m['id']}` **{self.formatear(m['cantidad'])}** silver — {m['motivo']} *(_{m['fecha'][:10]}_)*"
            for m in result.data
        ]
        embed = discord.Embed(
            title=f"⚠️ Multas de {target.display_name}",
            description="\n".join(lineas),
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Total pendiente: {self.formatear(total)} silver • Usa /quitar_multa <id> para cancelar una")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="saldar_multa", description="Paga una de tus multas con tu balance (Staff puede saldar la de otros)")
    @app_commands.describe(usuario="El miembro (por defecto, tú mismo)")
    async def saldar_multa(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        if usuario is None:
            usuario = ctx.author
        elif usuario != ctx.author and not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
            return await ctx.send("❌ Solo Oficiales y Guild Masters pueden saldar las multas de otros.", delete_after=5)

        balance_result, multas_result = await asyncio.gather(
            asyncio.to_thread(
                lambda: get_db().table('balances').select('balance')
                    .eq('usuario_id', str(usuario.id)).execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('multas').select('id, cantidad, motivo')
                    .eq('usuario_id', str(usuario.id)).eq('pagada', False)
                    .order('fecha').execute()
            )
        )
        saldo = balance_result.data[0]['balance'] if balance_result.data else 0
        multas = multas_result.data

        if not multas:
            return await ctx.send(f"✅ **{usuario.display_name}** no tiene multas pendientes.")

        view = SaldarMultaView(self, usuario, multas, saldo)
        await ctx.send(embed=self._embed_multas_saldo(usuario, multas, saldo), view=view)

    @commands.hybrid_command(name="saldar_todas_multas", description="Usa tu balance para pagar todas tus multas (Staff puede las de otros)")
    @app_commands.describe(usuario="El miembro (por defecto, tú mismo)")
    async def saldar_todas_multas(self, ctx, usuario: discord.Member = None):
        await ctx.defer()

        if usuario is None:
            usuario = ctx.author
        elif usuario != ctx.author and not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
            return await ctx.send("❌ Solo Oficiales y Guild Masters pueden saldar las multas de otros.", delete_after=5)

        balance_result, multas_result = await asyncio.gather(
            asyncio.to_thread(
                lambda: get_db().table('balances').select('balance')
                    .eq('usuario_id', str(usuario.id)).execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('multas').select('id, cantidad, motivo')
                    .eq('usuario_id', str(usuario.id)).eq('pagada', False)
                    .order('fecha').execute()
            )
        )
        saldo = balance_result.data[0]['balance'] if balance_result.data else 0
        multas = multas_result.data

        if not multas:
            return await ctx.send(f"✅ **{usuario.display_name}** no tiene multas pendientes.")
        if saldo <= 0:
            return await ctx.send(f"❌ **{usuario.display_name}** no tiene balance para saldar multas.")

        pagadas, no_pagadas, balance_usado, saldo_restante = [], [], 0, saldo
        for multa in multas:
            if saldo_restante >= multa['cantidad']:
                pagadas.append(multa)
                saldo_restante -= multa['cantidad']
                balance_usado += multa['cantidad']
            else:
                no_pagadas.append(multa)

        if not pagadas:
            return await ctx.send(
                f"❌ El balance de **{usuario.display_name}** (**{self.formatear(saldo)}** silver) "
                f"no alcanza ni para la multa más pequeña (**{self.formatear(multas[0]['cantidad'])}** silver)."
            )

        ids_pagadas = [m['id'] for m in pagadas]
        await asyncio.to_thread(
            lambda: get_db().table('multas').update({'pagada': True})
                .in_('id', ids_pagadas).execute()
        )
        await _actualizar_balance(usuario, -balance_usado, "pago_multas", f"Saldo de {len(pagadas)} multa(s)")

        embed = discord.Embed(
            title=f"⚖️ Multas saldadas — {usuario.display_name}",
            color=discord.Color.green() if not no_pagadas else discord.Color.orange()
        )
        embed.add_field(
            name=f"✅ Pagadas ({len(pagadas)})",
            value="\n".join(f"**{self.formatear(m['cantidad'])}** silver — {m['motivo']}" for m in pagadas),
            inline=False
        )
        if no_pagadas:
            embed.add_field(
                name=f"❌ Sin fondos suficientes ({len(no_pagadas)})",
                value="\n".join(f"**{self.formatear(m['cantidad'])}** silver — {m['motivo']}" for m in no_pagadas),
                inline=False
            )
        embed.add_field(
            name="Resumen",
            value=f"Silver usado: **{self.formatear(balance_usado)}**\nBalance restante: **{self.formatear(saldo_restante)}** silver",
            inline=False
        )
        embed.set_footer(text=f"Ejecutado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    def _embed_multas_saldo(self, usuario: discord.Member, multas: list, saldo: int) -> discord.Embed:
        total = sum(m['cantidad'] for m in multas)
        lineas = []
        for m in multas:
            icono = "✅" if saldo >= m['cantidad'] else "❌"
            lineas.append(f"{icono} **{self.formatear(m['cantidad'])}** silver — {m['motivo']}")
        embed = discord.Embed(
            title=f"⚠️ Multas de {usuario.display_name}",
            description="\n".join(lineas),
            color=discord.Color.orange()
        )
        embed.add_field(name="Balance disponible", value=f"**{self.formatear(saldo)}** silver", inline=True)
        embed.add_field(name="Total multas",        value=f"**{self.formatear(total)}** silver", inline=True)
        embed.set_footer(text="✅ balance suficiente  •  ❌ sin fondos  •  Selecciona con el menú")
        return embed

    @commands.hybrid_command(name="quitar_multa", description="Cancela una multa por su ID")
    @app_commands.describe(multa_id="ID de la multa (visible en /ver_multas)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def quitar_multa(self, ctx, multa_id: int):
        result = await asyncio.to_thread(
            lambda: get_db().table('multas').select('id, usuario_nombre, cantidad, motivo')
                .eq('id', multa_id).eq('pagada', False).execute()
        )
        if not result.data:
            return await ctx.send(f"❌ No existe una multa pendiente con ID `{multa_id}`.", delete_after=5)
        m = result.data[0]
        await asyncio.to_thread(
            lambda: get_db().table('multas').update({'pagada': True}).eq('id', multa_id).execute()
        )
        await ctx.send(
            f"✅ Multa `#{multa_id}` cancelada — **{m['usuario_nombre']}** | "
            f"{self.formatear(m['cantidad'])} silver | *{m['motivo']}*"
        )

    @commands.hybrid_command(name="remove_balance", description="Resetea el balance de un miembro a cero sin registrar transacción")
    @commands.has_any_role("Oficial", "Guild Master")
    async def remove_balance(self, ctx, usuario: discord.Member):
        multas_result = await asyncio.to_thread(
            lambda: get_db().table('multas').select('id, cantidad, motivo').eq('usuario_id', str(usuario.id)).eq('pagada', False).execute()
        )
        if multas_result.data:
            total_multas = sum(m['cantidad'] for m in multas_result.data)
            lineas = [f"• `#{m['id']}` {self.formatear(m['cantidad'])} silver — {m['motivo']}" for m in multas_result.data]
            embed = discord.Embed(
                title="⛔ Operación bloqueada — Multas pendientes",
                description=f"{usuario.mention} tiene **{len(multas_result.data)} multa(s)** por un total de **{self.formatear(total_multas)} silver**.\nResuélvelas antes de limpiar el balance.\n\n" + "\n".join(lineas),
                color=discord.Color.red()
            )
            embed.set_footer(text="Usa /quitar_multa <id> para cancelar una multa")
            return await ctx.send(embed=embed)
        await asyncio.to_thread(
            lambda: get_db().table('balances')
                .update({'balance': 0})
                .eq('usuario_id', str(usuario.id))
                .execute()
        )
        await ctx.send(f"♻️ Balance reseteado a 0 para {usuario.mention}.")

    @commands.hybrid_command(name="wipe_silver", description="⚠️ Borra TODOS los balances de silver del servidor")
    @commands.has_permissions(administrator=True)
    async def wipe_silver(self, ctx):
        await ctx.defer()
        await asyncio.to_thread(
            lambda: get_db().table('balances').delete().neq('usuario_id', '').execute()
        )
        await ctx.send(embed=discord.Embed(
            title="⚠️ WIPE DE SILVER COMPLETADO",
            description="Se han reseteado todos los balances de silver del servidor.",
            color=discord.Color.red()
        ))

    @commands.hybrid_command(name="wipe_asistencias", description="⚠️ Borra TODAS las asistencias de los miembros")
    @commands.has_permissions(administrator=True)
    async def wipe_asistencias(self, ctx):
        await ctx.defer()
        await asyncio.to_thread(
            lambda: get_db().table('asistencias').delete().neq('usuario_id', '').execute()
        )
        await ctx.send(embed=discord.Embed(
            title="⚠️ WIPE DE ASISTENCIAS COMPLETADO",
            description="Se han eliminado todos los registros de asistencia del servidor.",
            color=discord.Color.red()
        ))

class SaldarMultaView(discord.ui.View):
    def __init__(self, cog, usuario: discord.Member, multas: list, saldo: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.usuario = usuario
        self.multas = multas
        self.saldo = saldo

        options = []
        for m in multas[:25]:
            puede = saldo >= m['cantidad']
            options.append(discord.SelectOption(
                label=f"{cog.formatear(m['cantidad'])} silver",
                description=(m['motivo'] or "Sin motivo")[:100],
                value=str(m['id']),
                emoji="✅" if puede else "❌"
            ))

        select = discord.ui.Select(placeholder="Elige la multa a pagar...", options=options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction):
        multa_id = int(self._select.values[0])
        multa = next((m for m in self.multas if m['id'] == multa_id), None)
        if not multa:
            return await interaction.response.send_message("❌ Multa no encontrada.", ephemeral=True)

        if self.saldo < multa['cantidad']:
            return await interaction.response.send_message(
                f"❌ Balance insuficiente: tiene **{self.cog.formatear(self.saldo)}** silver "
                f"pero la multa es de **{self.cog.formatear(multa['cantidad'])}** silver.",
                ephemeral=True
            )

        await asyncio.to_thread(
            lambda: get_db().table('multas').update({'pagada': True}).eq('id', multa_id).execute()
        )
        await _actualizar_balance(self.usuario, -multa['cantidad'], "pago_multa", f"Multa: {multa['motivo']}")

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Multa saldada",
                description=(
                    f"Se descontaron **{self.cog.formatear(multa['cantidad'])}** silver "
                    f"del balance de {self.usuario.mention}.\n"
                    f"Motivo: *{multa['motivo']}*\n"
                    f"Balance restante: **{self.cog.formatear(self.saldo - multa['cantidad'])}** silver"
                ),
                color=discord.Color.green()
            ),
            view=self
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class AprobacionSplitView(discord.ui.View):
    def __init__(self, cog, *, solicitante, channel, guild, params, cerrar):
        super().__init__(timeout=3600)  # 1 hora para aprobar
        self.cog = cog
        self.solicitante = solicitante
        self.channel = channel
        self.guild = guild
        self.params = params
        self.cerrar = cerrar
        self.msg = None
        self.resuelto = False

    def _es_oficial(self, member) -> bool:
        return any(r.name in ("Oficial", "Guild Master") for r in member.roles)

    @discord.ui.button(label="Aprobar", emoji="✅", style=discord.ButtonStyle.green)
    async def aprobar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._es_oficial(interaction.user):
            return await interaction.response.send_message("❌ Solo un Oficial o Guild Master puede aprobar.", ephemeral=True)
        if self.resuelto:
            return await interaction.response.send_message("⚠️ Esta solicitud ya fue resuelta.", ephemeral=True)
        self.resuelto = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Split aprobado por {interaction.user.mention} — solicitado por {self.solicitante.mention}.",
            view=self
        )

        ok, payload = await self.cog._realizar_split(self.channel, self.guild, cerrar=self.cerrar, **self.params)
        if not ok:
            await self.channel.send(payload)
            return
        await self.channel.send(embed=payload)
        if self.cerrar:
            try:
                await self.channel.edit(locked=True, archived=True)
            except Exception:
                pass

    @discord.ui.button(label="Rechazar", emoji="🚫", style=discord.ButtonStyle.red)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._es_oficial(interaction.user):
            return await interaction.response.send_message("❌ Solo un Oficial o Guild Master puede rechazar.", ephemeral=True)
        if self.resuelto:
            return await interaction.response.send_message("⚠️ Esta solicitud ya fue resuelta.", ephemeral=True)
        self.resuelto = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"🚫 Split rechazado por {interaction.user.mention}. No se repartió nada.",
            view=self
        )

    async def on_timeout(self):
        if self.resuelto:
            return
        for child in self.children:
            child.disabled = True
        if self.msg:
            try:
                await self.msg.edit(content="⏱️ Solicitud de split expirada sin aprobación. No se repartió nada.", view=self)
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Silver(bot))

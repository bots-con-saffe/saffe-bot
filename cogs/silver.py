import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from db import get_db, get_balance_lock


async def _actualizar_balance(member: discord.Member, cantidad: int, tipo: str, motivo: str):
    user_id = str(member.id)
    nombre  = member.display_name

    async with get_balance_lock(user_id):
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('balance').eq('usuario_id', user_id).execute()
        )
        balance_actual = result.data[0]['balance'] if result.data else 0
        nuevo_balance  = balance_actual + cantidad

        await asyncio.to_thread(
            lambda: get_db().table('balances')
                .upsert({'usuario_id': user_id, 'usuario_nombre': nombre, 'balance': nuevo_balance}, on_conflict='usuario_id')
                .execute()
        )
        await asyncio.to_thread(
            lambda: get_db().table('transacciones')
                .insert({'usuario_id': user_id, 'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo})
                .execute()
        )


class Silver(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def formatear(self, cantidad: int) -> str:
        return f"{cantidad:,}".replace(",", ".")

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

        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('balance').eq('usuario_id', str(target.id)).execute()
        )
        saldo = result.data[0]['balance'] if result.data else 0
        await ctx.send(embed=discord.Embed(
            title=f"💰 Balance de {target.display_name}",
            description=f"**{self.formatear(saldo)}** silver",
            color=discord.Color.gold()
        ))

    @commands.hybrid_command(name="balance_total_gremio", description="Suma total de silver que el gremio debe pagar a los miembros")
    @commands.has_any_role("Oficial", "Guild Master")
    async def balance_total_gremio(self, ctx):
        await ctx.defer()
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('usuario_id, usuario_nombre, balance').execute()
        )
        if not result.data:
            return await ctx.send("📊 La base de datos de balances está vacía.")

        deuda_total = 0
        detalles = []
        for row in result.data:
            saldo = row.get('balance', 0)
            if saldo > 0:
                deuda_total += saldo
                detalles.append((row.get('usuario_nombre', 'Desconocido'), saldo))

        if deuda_total == 0:
            return await ctx.send(embed=discord.Embed(
                title="📈 Balance General del Gremio",
                description="✅ **¡El gremio está al día!** No se le debe silver a nadie.",
                color=discord.Color.green()
            ))

        detalles.sort(key=lambda x: -x[1])
        lineas = [f"• **{nombre}**: {self.formatear(saldo)} silver" for nombre, saldo in detalles[:30]]
        if len(detalles) > 30:
            lineas.append(f"*... y {len(detalles) - 30} usuarios más.*")

        embed = discord.Embed(
            title="📊 Reporte de Deuda Pendiente del Gremio",
            description=f"💰 **Total a Pagar:** {self.formatear(deuda_total)} silver\n👥 **Jugadores con saldo:** {len(detalles)}",
            color=discord.Color.red()
        )
        embed.add_field(name="📋 Desglose de Cuentas Pendientes", value="\n".join(lineas), inline=False)
        embed.set_footer(text="Usa /pay [usuario] para saldar la cuenta de alguien.")
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
    @commands.has_any_role("Oficial", "Guild Master")
    async def split(self, ctx, bolsas: str, loot: str, costo_mapa: str = "0", tax_porcentaje: int = 15, venta_rapida: int = 0, excluir: discord.Member = None):
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
            return await ctx.send("❌ No hay miembros anotados para efectuar el reparto.")

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

        lista_pagos = ""
        for p in participantes:
            await _actualizar_balance(p, por_persona, "split", f"Split: {ctx.channel.name}")
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

        # Cerrar actividad
        pings_cog = self.bot.get_cog("PingsAlbion")
        if pings_cog:
            await pings_cog.actualizar_mensaje(ctx.channel, registro, estado="finalizada")

        await asyncio.to_thread(
            lambda: get_db().table('registros_activos').delete().eq('hilo_id', hilo_id).execute()
        )

        embed = discord.Embed(title="💰 Reparto Avanzado y Asistencia Registrada", color=discord.Color.green())
        resumen = (
            f"**Bolsas iniciales:** {self.formatear(v_bolsas)}\n"
            f"**Loot neto recaudado:** {self.formatear(loot_inicial)}\n"
            f"**Costo de mapa:** -{self.formatear(v_costo_mapa)} *(cobrado de las bolsas primero)*\n"
            f"**Tax gremio ({tax_porcentaje}% del loot):** -{self.formatear(tax)}\n"
            f"**Total neto a repartir:** {self.formatear(total_neto)}"
        )
        embed.add_field(name="Resumen de Operación", value=resumen, inline=False)
        embed.add_field(name="👥 Distribución Detallada", value=lista_pagos, inline=False)
        embed.set_footer(text="Contenido completado. Hilo archivado.")

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
    @commands.has_any_role("Oficial", "Guild Master")
    async def split_medio(self, ctx, bolsas: str, loot: str, costo_mapa: str = "0", tax_porcentaje: int = 15, venta_rapida: int = 0, excluir: discord.Member = None):
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
            return await ctx.send("❌ No hay miembros anotados para efectuar el reparto parcial.")

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

        lista_pagos = ""
        for p in participantes:
            await _actualizar_balance(p, por_persona, "split_medio", f"Split Parcial: {ctx.channel.name}")
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
        embed.set_footer(text="Usa /desanotar para liberar puestos antes del próximo split.")
        await ctx.send(embed=embed)

    # --- GESTIÓN DE BALANCES ---

    @commands.hybrid_command(name="pay", description="Salda la deuda pendiente de un miembro")
    @commands.has_any_role("Oficial", "Guild Master")
    async def pay(self, ctx, usuario: discord.Member):
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('balance').eq('usuario_id', str(usuario.id)).execute()
        )
        if not result.data or result.data[0]['balance'] <= 0:
            return await ctx.send("❌ Este miembro no tiene balance pendiente.")
        deuda = result.data[0]['balance']
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
    async def removebalance(self, ctx, usuario: discord.Member, cantidad: str, *, motivo: str = "Ajuste manual"):
        valor = self.convertir_unidad(cantidad)
        await _actualizar_balance(usuario, -valor, "ajuste_manual", motivo)
        await ctx.send(f"✅ Restados **{self.formatear(valor)}** silver a {usuario.mention}.")

    @commands.hybrid_command(name="remove_balance", description="Resetea el balance de un miembro a cero sin registrar transacción")
    @commands.has_any_role("Oficial", "Guild Master")
    async def remove_balance(self, ctx, usuario: discord.Member):
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

async def setup(bot):
    await bot.add_cog(Silver(bot))

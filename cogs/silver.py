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
                detalles.append((row.get('usuario_nombre', 'Desconocido'), saldo))

        if deuda_total == 0:
            return await ctx.send(embed=discord.Embed(
                title="📈 Balance General del Gremio",
                description="✅ **¡El gremio está al día!** No se le debe silver a nadie.",
                color=discord.Color.green()
            ))

        detalles.sort(key=lambda x: -x[1])
        lineas = [f"• **{nombre}**: {self.formatear(saldo)} silver" for nombre, saldo in detalles]

        embed = discord.Embed(
            title="📊 Reporte de Deuda Pendiente del Gremio",
            description=f"💰 **Total a Pagar:** {self.formatear(deuda_total)} silver\n👥 **Jugadores con saldo:** {len(detalles)}",
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

    @commands.hybrid_command(name="expropiar", description="Quita TODO el balance de un miembro")
    @app_commands.describe(usuario="El miembro", motivo="Razón de la expropiación")
    @commands.has_any_role("Oficial", "Guild Master")
    async def expropiar(self, ctx, usuario: discord.Member, *, motivo: str):
        result = await asyncio.to_thread(
            lambda: get_db().table('balances').select('balance').eq('usuario_id', str(usuario.id)).execute()
        )
        saldo = result.data[0]['balance'] if result.data else 0
        if saldo <= 0:
            return await ctx.send(f"❌ {usuario.display_name} no tiene silver para expropiar.", delete_after=5)
        await _actualizar_balance(usuario, -saldo, "expropiacion", motivo)
        embed = discord.Embed(title="⚖️ Expropiación Total", color=discord.Color.dark_red())
        embed.add_field(name="Miembro",   value=usuario.mention,                          inline=True)
        embed.add_field(name="Cantidad",  value=f"**{self.formatear(saldo)}** silver",    inline=True)
        embed.add_field(name="Motivo",    value=motivo,                                   inline=False)
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

async def setup(bot):
    await bot.add_cog(Silver(bot))

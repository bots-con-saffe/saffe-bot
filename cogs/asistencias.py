import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from datetime import datetime, timezone, timedelta
from db import get_db


def _inicio_periodo(periodo: str):
    """Retorna timestamp ISO del inicio del periodo, o None para 'total'."""
    hoy = datetime.now(timezone.utc)
    if periodo == "semana":
        lunes = hoy - timedelta(days=hoy.weekday())
        return lunes.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if periodo == "bisemanal":
        lunes = hoy - timedelta(days=hoy.weekday())
        inicio_bi = lunes - timedelta(days=7)
        return inicio_bi.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return None  # "total" → sin filtro


class Asistencias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def periodo_autocomplete(self, interaction, current):
        opciones = ["semana", "bisemanal", "total"]
        return [app_commands.Choice(name=o, value=o) for o in opciones if current.lower() in o.lower()]

    async def indice_asistencia_autocomplete(self, interaction: discord.Interaction, current: str):
        usuario_sel = interaction.namespace.usuario
        if not usuario_sel:
            return []
        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('id, fecha, registros_actividad(tipo, nombre_contenido)')
                .eq('usuario_id', str(usuario_sel.id))
                .order('fecha', desc=True)
                .limit(25)
                .execute()
        )
        choices = []
        for i, row in enumerate(result.data):
            ra = row.get('registros_actividad') or {}
            nombre = ra.get('nombre_contenido') or ra.get('tipo') or 'N/A'
            fecha = row['fecha'][:10]
            label = f"[{i}] {nombre} - {fecha}"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=str(row['id'])))
        return choices[:25]

    @commands.hybrid_command(name="asistencias", description="Muestra el historial de actividades de un miembro")
    @app_commands.describe(usuario="Miembro a consultar (por defecto tú mismo)")
    async def asistencias(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)
        target = usuario or ctx.author

        if target != ctx.author:
            if not any(r.name in ["Oficial", "Guild Master"] for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden consultar las asistencias de otros.", delete_after=5)

        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('id, fecha, registros_actividad(tipo, nombre_contenido, lugar, info)')
                .eq('usuario_id', str(target.id))
                .order('fecha', desc=True)
                .limit(15)
                .execute()
        )

        if not result.data:
            return await ctx.send(f"**{target.display_name}** no tiene asistencias registradas.", delete_after=7)

        embed = discord.Embed(
            title=f"📋 Asistencias de {target.display_name}",
            description=f"Últimas {len(result.data)} actividades",
            color=discord.Color.blurple()
        )
        for i, row in enumerate(result.data):
            ra = row.get('registros_actividad') or {}
            nombre = ra.get('nombre_contenido') or ra.get('tipo', 'N/A')
            detalle = ra.get('lugar') or ra.get('info') or "Sin detalles"
            fecha = row['fecha'][:10]
            embed.add_field(name=f"[{i}] {nombre} — {fecha}", value=detalle, inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="borrar_asistencia", description="Elimina una asistencia específica de un miembro")
    @app_commands.describe(usuario="El miembro", indice="Asistencia a eliminar")
    @app_commands.autocomplete(indice=indice_asistencia_autocomplete)
    @commands.has_any_role("Oficial", "Guild Master")
    async def borrar_asistencia(self, ctx, usuario: discord.Member, indice: str):
        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .delete()
                .eq('id', indice)
                .eq('usuario_id', str(usuario.id))
                .execute()
        )
        if result.data:
            await ctx.send(f"✅ Asistencia eliminada de {usuario.mention}.")
        else:
            await ctx.send("❌ No se encontró la asistencia especificada.")

    @commands.hybrid_command(name="top", description="Ranking de miembros con más actividades en el periodo")
    @app_commands.autocomplete(periodo=periodo_autocomplete)
    async def top(self, ctx, periodo: str = "semana"):
        await ctx.defer()

        periodo = periodo.lower()
        if periodo not in ("semana", "bisemanal", "total"):
            return await ctx.send("❌ El periodo debe ser `semana`, `bisemanal` o `total`.", delete_after=5)

        desde = _inicio_periodo(periodo)
        query = get_db().table('asistencias').select('usuario_id, usuario_nombre, registros_actividad(multiplicador)')
        if desde:
            query = query.gte('fecha', desde)

        result = await asyncio.to_thread(lambda: query.execute())

        if not result.data:
            return await ctx.send(f"No hay asistencias registradas para el periodo `{periodo}`.", delete_after=5)

        conteo: dict[str, dict] = {}
        for row in result.data:
            uid = row['usuario_id']
            ra = row.get('registros_actividad') or {}
            mult = ra.get('multiplicador') or 1
            if uid not in conteo:
                conteo[uid] = {'nombre': row['usuario_nombre'], 'count': 0}
            conteo[uid]['count'] += mult

        ranking = sorted(conteo.values(), key=lambda x: x['count'], reverse=True)[:25]

        embed = discord.Embed(title=f"🏆 Ranking de Asistencia ({periodo.upper()})", color=discord.Color.gold())
        for i, entry in enumerate(ranking):
            embed.add_field(name=f"{i+1}. {entry['nombre']}", value=f"✨ **{entry['count']} puntos**", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="lista_asistencias_total", description="Muestra la actividad de todos los miembros con roles de gremio")
    @app_commands.autocomplete(periodo=periodo_autocomplete)
    @commands.has_any_role("Oficial", "Guild Master")
    async def lista_asistencias_total(self, ctx, periodo: str = "semana"):
        await ctx.defer(ephemeral=False)

        periodo = periodo.lower()
        desde = _inicio_periodo(periodo)
        query = get_db().table('asistencias').select('usuario_id, registros_actividad(multiplicador)')
        if desde:
            query = query.gte('fecha', desde)

        result = await asyncio.to_thread(lambda: query.execute())

        puntos_por_usuario: dict[str, int] = {}
        for row in result.data:
            uid = row['usuario_id']
            ra = row.get('registros_actividad') or {}
            mult = ra.get('multiplicador') or 1
            puntos_por_usuario[uid] = puntos_por_usuario.get(uid, 0) + mult

        roles_gremio = ["Miembro", "Ava Core", "PvE Content", "PvP Content"]
        lista = []
        for miembro in ctx.guild.members:
            if miembro.bot:
                continue
            if any(discord.utils.get(miembro.roles, name=r) for r in roles_gremio):
                puntos = puntos_por_usuario.get(str(miembro.id), 0)
                lista.append({"nombre": miembro.display_name, "puntos": puntos, "id": str(miembro.id)})

        if not lista:
            return await ctx.interaction.followup.send("❌ No se encontraron miembros con los roles del gremio en el servidor.")

        lista.sort(key=lambda x: (-x["puntos"], x["nombre"]))

        lineas = []
        for m in lista:
            marcador = "🔴 INACTIVO (0 pts)" if m["puntos"] == 0 else f"🟢 {m['puntos']} pts"
            lineas.append(f"• **{m['nombre']}** ({marcador}) - ID: `{m['id']}`")

        chunks = [lineas[i:i + 20] for i in range(0, len(lineas), 20)]
        embed_1 = discord.Embed(
            title=f"📋 Control de Actividad Gremial ({periodo.upper()}) - Parte 1/{len(chunks)}",
            description="Lista de actividad oficial del gremio. Los rangos bajos están sujetos a revisión y limpieza.\n\n" + "\n".join(chunks[0]),
            color=discord.Color.dark_red()
        )
        await ctx.interaction.followup.send(embed=embed_1)

        for index, chunk in enumerate(chunks[1:], start=2):
            embed = discord.Embed(
                title=f"📋 Control de Actividad Gremial ({periodo.upper()}) - Parte {index}/{len(chunks)}",
                description="\n".join(chunk),
                color=discord.Color.dark_red()
            )
            await ctx.interaction.followup.send(embed=embed)

    @commands.hybrid_command(name="asistencias_rango", description="Puntos acumulados entre dos fechas exactas")
    @app_commands.describe(desde="Fecha inicio DD/MM/YYYY", hasta="Fecha fin DD/MM/YYYY")
    @commands.has_any_role("Oficial", "Guild Master")
    async def asistencias_rango(self, ctx, desde: str, hasta: str):
        await ctx.defer()
        try:
            fecha_inicio = datetime.strptime(desde, "%d/%m/%Y").replace(tzinfo=timezone.utc)
            fecha_fin = datetime.strptime(hasta, "%d/%m/%Y").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except ValueError:
            return await ctx.send("❌ Formato de fecha incorrecto. Usa: `DD/MM/YYYY` (Ej: 01/05/2026).")

        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('usuario_id, usuario_nombre, registros_actividad(multiplicador)')
                .gte('fecha', fecha_inicio.isoformat())
                .lte('fecha', fecha_fin.isoformat())
                .execute()
        )

        if not result.data:
            return await ctx.send("No hay registros en ese rango.")

        conteo: dict[str, dict] = {}
        for row in result.data:
            uid = row['usuario_id']
            ra = row.get('registros_actividad') or {}
            mult = ra.get('multiplicador') or 1
            if uid not in conteo:
                conteo[uid] = {'nombre': row['usuario_nombre'], 'count': 0}
            conteo[uid]['count'] += mult

        ranking = sorted(conteo.values(), key=lambda x: x['count'])

        lineas = []
        for entry in ranking:
            status = "❌" if entry['count'] == 0 else "⚔️"
            lineas.append(f"{status} **{entry['nombre']}**: {entry['count']} puntos")

        chunks = [lineas[i:i + 25] for i in range(0, len(lineas), 25)]
        for index, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📅 Asistencias del {desde} al {hasta}",
                description="\n".join(chunk),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="sorteo", description="Ganador aleatorio ponderado por tickets de asistencia")
    @commands.has_any_role("Oficial", "Guild Master")
    async def sorteo(self, ctx):
        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias').select('usuario_id').execute()
        )
        if not result.data:
            return await ctx.send("❌ Sin registros de asistencia.")
        pool = [row['usuario_id'] for row in result.data]
        ganador_id = random.choice(pool)
        ganador = ctx.guild.get_member(int(ganador_id))
        await ctx.send(embed=discord.Embed(
            title="🎉 ¡GANADOR! 🎉",
            description=f"El afortunado es: {ganador.mention if ganador else f'ID: {ganador_id}'}",
            color=discord.Color.gold()
        ))

    @commands.hybrid_command(name="reporte", description="Resumen de actividades y asistencias del periodo")
    @app_commands.describe(periodo="semana o bisemanal (por defecto: semana)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def reporte(self, ctx, periodo: str = "semana"):
        await ctx.defer()

        periodo = periodo.lower()
        desde = _inicio_periodo(periodo)
        if desde is None:
            return await ctx.send("❌ El periodo debe ser `semana` o `bisemanal`.", delete_after=5)

        titulo = "esta semana" if periodo == "semana" else "las últimas 2 semanas"

        actividades_result, asistencias_result, silver_result = await asyncio.gather(
            asyncio.to_thread(
                lambda: get_db().table('registros_actividad')
                    .select('tipo')
                    .eq('guild_id', str(ctx.guild.id))
                    .gte('creado_en', desde)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('asistencias')
                    .select('usuario_id')
                    .gte('fecha', desde)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: get_db().table('transacciones')
                    .select('cantidad')
                    .eq('tipo', 'split')
                    .gte('fecha', desde)
                    .execute()
            )
        )

        total_actividades = len(actividades_result.data)
        total_silver = sum(t['cantidad'] for t in silver_result.data if t['cantidad'] > 0)
        participantes_unicos = len(set(r['usuario_id'] for r in asistencias_result.data))

        tipos: dict[str, int] = {}
        for row in actividades_result.data:
            tipo = row['tipo'].capitalize()
            tipos[tipo] = tipos.get(tipo, 0) + 1

        embed = discord.Embed(title=f"📊 Reporte — {titulo.capitalize()}", color=discord.Color.blurple())
        embed.add_field(name="Actividades realizadas", value=str(total_actividades), inline=True)
        embed.add_field(name="Participantes únicos", value=str(participantes_unicos), inline=True)
        embed.add_field(name="Silver repartido", value=f"{total_silver:,}".replace(",", "."), inline=True)

        if tipos:
            tipos_str = "\n".join(f"• {tipo}: {count}" for tipo, count in sorted(tipos.items(), key=lambda x: x[1], reverse=True))
            embed.add_field(name="Por tipo de actividad", value=tipos_str, inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Asistencias(bot))

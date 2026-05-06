import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timezone, timedelta
from db import get_db


def inicio_semana() -> str:
    hoy = datetime.now(timezone.utc)
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def inicio_mes() -> str:
    hoy = datetime.now(timezone.utc)
    return hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class Asistencias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- HISTORIAL DE ASISTENCIAS DE UN MIEMBRO ---

    @commands.hybrid_command(name="asistencias", description="Muestra el historial de actividades de un miembro")
    @app_commands.describe(usuario="Miembro a consultar (por defecto tú mismo)")
    async def asistencias(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        target = usuario or ctx.author

        # Si consulta a otro, requiere rol
        if target != ctx.author:
            roles_permitidos = ["Oficial", "Guild Master"]
            if not any(r.name in roles_permitidos for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden consultar las asistencias de otros.", delete_after=5)

        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('usuario_nombre, fecha, registros_actividad(tipo, info)')
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

        for row in result.data:
            tipo = row['registros_actividad']['tipo'].capitalize()
            fecha = row['fecha'][:10]
            info = row['registros_actividad']['info'] or "Sin detalles"
            embed.add_field(name=f"{tipo} — {fecha}", value=info, inline=False)

        await ctx.send(embed=embed)

    # --- RANKING DE ASISTENCIAS ---

    @commands.hybrid_command(name="top", description="Ranking de miembros con más actividades en el periodo")
    @app_commands.describe(periodo="semana o mes (por defecto: semana)")
    async def top(self, ctx, periodo: str = "semana"):
        await ctx.defer()

        periodo = periodo.lower()
        if periodo not in ("semana", "mes"):
            return await ctx.send("❌ El periodo debe ser `semana` o `mes`.", delete_after=5)

        desde = inicio_semana() if periodo == "semana" else inicio_mes()
        titulo = "esta semana" if periodo == "semana" else "este mes"

        result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('usuario_id, usuario_nombre')
                .gte('fecha', desde)
                .execute()
        )

        if not result.data:
            return await ctx.send(f"No hay asistencias registradas {titulo}.", delete_after=5)

        # Contar asistencias por usuario
        conteo: dict[str, dict] = {}
        for row in result.data:
            uid = row['usuario_id']
            if uid not in conteo:
                conteo[uid] = {'nombre': row['usuario_nombre'], 'count': 0}
            conteo[uid]['count'] += 1

        ranking = sorted(conteo.values(), key=lambda x: x['count'], reverse=True)[:10]

        embed = discord.Embed(
            title=f"🏆 Top asistencias — {titulo.capitalize()}",
            color=discord.Color.gold()
        )

        medallas = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(ranking):
            prefijo = medallas[i] if i < 3 else f"**{i+1}.**"
            embed.add_field(
                name=f"{prefijo} {entry['nombre']}",
                value=f"{entry['count']} actividad{'es' if entry['count'] != 1 else ''}",
                inline=False
            )

        await ctx.send(embed=embed)

    # --- REPORTE DEL PERIODO ---

    @commands.hybrid_command(name="reporte", description="Resumen de actividades y asistencias del periodo")
    @app_commands.describe(periodo="semana o mes (por defecto: semana)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def reporte(self, ctx, periodo: str = "semana"):
        await ctx.defer()

        periodo = periodo.lower()
        if periodo not in ("semana", "mes"):
            return await ctx.send("❌ El periodo debe ser `semana` o `mes`.", delete_after=5)

        desde = inicio_semana() if periodo == "semana" else inicio_mes()
        titulo = "esta semana" if periodo == "semana" else "este mes"

        # Actividades realizadas
        actividades_result = await asyncio.to_thread(
            lambda: get_db().table('registros_actividad')
                .select('tipo')
                .eq('guild_id', str(ctx.guild.id))
                .gte('creado_en', desde)
                .execute()
        )

        # Asistencias del periodo
        asistencias_result = await asyncio.to_thread(
            lambda: get_db().table('asistencias')
                .select('usuario_id, usuario_nombre')
                .gte('fecha', desde)
                .execute()
        )

        # Silver repartido en el periodo
        silver_result = await asyncio.to_thread(
            lambda: get_db().table('transacciones')
                .select('cantidad')
                .eq('tipo', 'split')
                .gte('fecha', desde)
                .execute()
        )

        total_actividades = len(actividades_result.data)
        total_asistencias = len(asistencias_result.data)
        total_silver = sum(t['cantidad'] for t in silver_result.data if t['cantidad'] > 0)

        # Contar tipo de actividades
        tipos: dict[str, int] = {}
        for row in actividades_result.data:
            tipo = row['tipo'].capitalize()
            tipos[tipo] = tipos.get(tipo, 0) + 1

        # Participantes únicos
        participantes_unicos = len(set(r['usuario_id'] for r in asistencias_result.data))

        embed = discord.Embed(
            title=f"📊 Reporte — {titulo.capitalize()}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Actividades realizadas", value=str(total_actividades), inline=True)
        embed.add_field(name="Participantes únicos", value=str(participantes_unicos), inline=True)
        embed.add_field(name="Total asistencias", value=str(total_asistencias), inline=True)
        embed.add_field(
            name="Silver repartido",
            value=f"{total_silver:,}".replace(",", "."),
            inline=True
        )

        if tipos:
            tipos_str = "\n".join(f"• {tipo}: {count}" for tipo, count in sorted(tipos.items(), key=lambda x: x[1], reverse=True))
            embed.add_field(name="Por tipo de actividad", value=tipos_str, inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Asistencias(bot))

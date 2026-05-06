import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from db import get_db


class PingsAlbion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Mapeo thread_id -> registro_actividad_id para que callout pueda guardar asistencias
        self.active_registros: dict[int, int] = {}

    # --- PLANTILLAS ---

    @commands.hybrid_command(name="crear_plantilla", description="Crea o actualiza una plantilla de actividad")
    @app_commands.describe(
        nombre="Nombre de la actividad (ej: dungeon)",
        puestos="Puestos separados por comas (ej: Tanque, Healer, Dps, Dps)"
    )
    @commands.has_permissions(administrator=True)
    async def crear_plantilla(self, ctx, nombre: str, *, puestos: str):
        await ctx.defer(ephemeral=True)
        try:
            await ctx.message.delete()
        except: pass

        lista_puestos = [p.strip() for p in puestos.split(",")]

        await asyncio.to_thread(
            lambda: get_db().table('actividades')
                .upsert({'nombre': nombre.lower(), 'puestos': lista_puestos}, on_conflict='nombre')
                .execute()
        )
        await ctx.send(f"✅ Plantilla **{nombre}** guardada con {len(lista_puestos)} puestos.", delete_after=5)

    @commands.hybrid_command(name="plantillas", description="Lista todas las plantillas de actividades disponibles")
    async def listar_plantillas(self, ctx):
        await ctx.defer()
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades').select('nombre, puestos').execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay plantillas creadas todavía.", delete_after=5)

        embed = discord.Embed(title="📋 Plantillas de actividades", color=discord.Color.blurple())
        for item in result.data:
            puestos_str = ", ".join(item['puestos'])
            embed.add_field(name=item['nombre'].capitalize(), value=puestos_str, inline=False)
        await ctx.send(embed=embed)

    # --- PING DE ACTIVIDAD ---

    @commands.hybrid_command(name="ping", description="Lanza una actividad con lista de inscripción")
    @app_commands.describe(
        tipo="Tipo de actividad (debe existir como plantilla)",
        rol_ping="Rol a mencionar además de @Miembro (opcional)",
        info="Información adicional sobre la actividad"
    )
    @commands.has_permissions(manage_messages=True)
    async def ping_dinamico(self, ctx, tipo: str, rol_ping: discord.Role = None, *, info: str = "Sin detalles adicionales"):
        await ctx.defer()
        try:
            await ctx.message.delete()
        except: pass

        # Cargar plantilla desde Supabase
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades')
                .select('puestos')
                .eq('nombre', tipo.lower())
                .execute()
        )

        if not result.data:
            await ctx.send(f"❌ La actividad `{tipo}` no existe. Usa `/plantillas` para ver las disponibles.", delete_after=7)
            return

        puestos_nombres = result.data[0]['puestos']
        participantes = {i + 1: None for i in range(len(puestos_nombres))}

        # Guardar registro de la actividad
        reg_result = await asyncio.to_thread(
            lambda: get_db().table('registros_actividad')
                .insert({
                    'guild_id': str(ctx.guild.id),
                    'tipo': tipo.lower(),
                    'info': info,
                    'creado_por': str(ctx.author.id)
                })
                .execute()
        )
        registro_id = reg_result.data[0]['id']

        def generar_embed():
            desc = ""
            for i, nombre in enumerate(puestos_nombres, 1):
                user = participantes[i]
                mencion = user.mention if user else "---"
                desc += f"**({i}) {nombre}**: {mencion}\n"
            embed = discord.Embed(
                title=f"⚔️ {tipo.upper()}",
                description=desc,
                color=discord.Color.green()
            )
            embed.add_field(name="Información", value=info)
            return embed

        rol_miembro = discord.utils.get(ctx.guild.roles, name="Miembro")
        mencion_final = ""
        if rol_ping:
            mencion_final += f"{rol_ping.mention} "
        if rol_miembro:
            mencion_final += f"{rol_miembro.mention}"

        # Se envía al canal directamente para que create_thread funcione tanto con ! como con /
        msg_lista = await ctx.channel.send(
            content=mencion_final if mencion_final else None,
            embed=generar_embed()
        )
        # Confirmar la interacción slash si aplica
        if ctx.interaction:
            await ctx.send("✅", ephemeral=True, delete_after=1)

        hilo = await msg_lista.create_thread(name=f"Inscripción - {tipo}", auto_archive_duration=60)
        await hilo.send("📢 **Escribe el número del puesto para anotarte | Usa -número para salir**")

        # Registrar el hilo para que callout pueda guardar asistencias
        self.active_registros[hilo.id] = registro_id

        def check(m):
            return m.channel.id == hilo.id and not m.author.bot

        while True:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=7200)
                contenido = msg.content.strip()
                usuario = msg.author

                roles_oficial = ["Oficial", "Guild Master"]
                es_oficial = any(r.name in roles_oficial for r in usuario.roles)

                # Oficial inscribe a otro: número @mención
                if es_oficial and msg.mentions and contenido.split()[0].isdigit():
                    try:
                        await msg.delete()
                    except: pass
                    num = int(contenido.split()[0])
                    objetivo = msg.mentions[0]
                    if num in participantes:
                        if participantes[num] is not None and participantes[num] != objetivo:
                            nombre_rol = puestos_nombres[num - 1]
                            await hilo.send(
                                f"❌ El puesto **{nombre_rol}** ya está ocupado por {participantes[num].mention}.",
                                delete_after=5
                            )
                        else:
                            for p in participantes:
                                if participantes[p] == objetivo:
                                    participantes[p] = None
                            participantes[num] = objetivo
                            await msg_lista.edit(embed=generar_embed())
                    else:
                        await hilo.send(f"❌ El puesto {num} no existe en esta lista.", delete_after=3)

                # Salirse de un puesto: -número
                elif contenido.startswith("-") and contenido[1:].isdigit():
                    try:
                        await msg.delete()
                    except: pass
                    num = int(contenido[1:])
                    if participantes.get(num) == usuario:
                        participantes[num] = None
                        await msg_lista.edit(embed=generar_embed())

                # Anotarse en un puesto: número
                elif contenido.isdigit():
                    try:
                        await msg.delete()
                    except: pass
                    num = int(contenido)
                    if num in participantes:
                        if participantes[num] is not None:
                            if participantes[num] != usuario:
                                nombre_rol = puestos_nombres[num - 1]
                                dueño_actual = participantes[num].display_name
                                try:
                                    await usuario.send(
                                        f"❌ El puesto **{num} ({nombre_rol})** ya está ocupado por **{dueño_actual}**."
                                    )
                                except discord.Forbidden:
                                    await hilo.send(
                                        f"❌ {usuario.mention}, el puesto **{nombre_rol}** ya está ocupado.",
                                        delete_after=5
                                    )
                        else:
                            for p in participantes:
                                if participantes[p] == usuario:
                                    participantes[p] = None
                            participantes[num] = usuario
                            await msg_lista.edit(embed=generar_embed())
                    else:
                        await hilo.send(f"❌ El puesto {num} no existe en esta lista.", delete_after=3)

            except asyncio.TimeoutError:
                self.active_registros.pop(hilo.id, None)
                break

    # --- MASS PING ---

    @commands.hybrid_command(name="mass", description="Pingea a todos los inscritos en el hilo de la actividad")
    @app_commands.describe(mensaje="Mensaje a enviar junto con las menciones")
    @commands.has_permissions(manage_messages=True)
    async def mass_ping(self, ctx, *, mensaje: str = "¡Log in ya salimos!"):
        await ctx.defer()
        try:
            await ctx.message.delete()
        except: pass

        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Este comando solo funciona dentro del hilo de una actividad.", delete_after=5)

        try:
            parent_msg = await ctx.channel.parent.fetch_message(ctx.channel.id)
            if parent_msg.embeds:
                embed = parent_msg.embeds[0]
                menciones = []
                for line in embed.description.split("\n"):
                    if "<@" in line:
                        start = line.find("<@")
                        end = line.find(">", start) + 1
                        menciones.append(line[start:end])

                if menciones:
                    await ctx.send(f"📢 {' '.join(menciones)}\n**{mensaje}**")
                else:
                    await ctx.send("❌ No hay nadie anotado todavía.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Error al buscar la lista: {e}", delete_after=5)


async def setup(bot):
    await bot.add_cog(PingsAlbion(bot))

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from db import get_db


class PingsAlbion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def template_autocomplete(self, interaction: discord.Interaction, current: str):
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades').select('nombre').execute()
        )
        return [
            app_commands.Choice(name=row['nombre'].upper(), value=row['nombre'])
            for row in result.data if current.lower() in row['nombre'].lower()
        ][:25]

    # --- PLANTILLAS ---

    @commands.hybrid_command(name="crear_plantilla", description="Crea o actualiza una composición de roles")
    @app_commands.describe(nombre="Nombre de la actividad (ej: dungeon)", puestos="Puestos separados por comas (ej: Tanque, Healer, Dps)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def crear_plantilla(self, ctx, nombre: str, *, puestos: str):
        lista_puestos = [p.strip() for p in puestos.split(",")]
        await asyncio.to_thread(
            lambda: get_db().table('actividades')
                .upsert({'nombre': nombre.lower(), 'puestos': lista_puestos}, on_conflict='nombre')
                .execute()
        )
        await ctx.send(f"✅ Plantilla **{nombre}** guardada.", delete_after=5)

    @commands.hybrid_command(name="borrar_plantilla", description="Elimina una composición guardada del bot")
    @app_commands.describe(nombre="Nombre de la plantilla a eliminar")
    @app_commands.autocomplete(nombre=template_autocomplete)
    @commands.has_any_role("Oficial", "Guild Master")
    async def borrar_plantilla(self, ctx, nombre: str):
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades')
                .delete()
                .eq('nombre', nombre.lower())
                .execute()
        )
        if result.data:
            await ctx.send(f"🗑️ La plantilla **{nombre.upper()}** ha sido eliminada.")
        else:
            await ctx.send(f"❌ No se encontró ninguna plantilla llamada `{nombre}`.", delete_after=5)

    @commands.hybrid_command(name="plantillas", description="Lista todas las composiciones disponibles")
    async def plantillas(self, ctx):
        await ctx.defer()
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades').select('nombre, puestos').execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay plantillas creadas todavía.", delete_after=5)

        embed = discord.Embed(title="📋 COMPOSICIONES", color=discord.Color.blue())
        for item in result.data:
            puestos_str = ", ".join(item['puestos'])
            embed.add_field(name=f"⚔️ {item['nombre'].upper()}", value=f"**Puestos:** {puestos_str}", inline=False)
        await ctx.send(embed=embed)

    # --- PING DE ACTIVIDAD ---

    @commands.hybrid_command(name="ping", description="Lanza una actividad con lista de inscripción")
    @app_commands.describe(
        tipo="Plantilla de la actividad",
        nombre_contenido="Nombre descriptivo (Ej: Ava 8.1, Dungeon T6)",
        fecha="Hora y día (Ej: Hoy 21:00)",
        lugar="Mapa o zona (Ej: BZ Mists)",
        rol="Rol a mencionar (opcional)",
        link_build="Link o canal de la build (opcional)"
    )
    @app_commands.autocomplete(tipo=template_autocomplete)
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def ping(self, ctx, tipo: str, nombre_contenido: str, fecha: str, lugar: str, rol: discord.Role = None, link_build: str = None):
        tipo = tipo.lower()
        result = await asyncio.to_thread(
            lambda: get_db().table('actividades').select('puestos').eq('nombre', tipo).execute()
        )
        if not result.data:
            return await ctx.send(f"❌ No existe la plantilla `{tipo}`.")

        puestos = result.data[0]['puestos']
        participantes = {str(i + 1): None for i in range(len(puestos))}
        multiplicador = 2 if "ava" in nombre_contenido.lower() else 1

        # Registrar la actividad en registros_actividad
        reg_result = await asyncio.to_thread(
            lambda: get_db().table('registros_actividad')
                .insert({
                    'guild_id': str(ctx.guild.id),
                    'tipo': tipo,
                    'info': f"{nombre_contenido} en {lugar}",
                    'creado_por': str(ctx.author.id),
                    'nombre_contenido': nombre_contenido,
                    'lugar': lugar,
                    'link_build': link_build,
                    'multiplicador': multiplicador
                })
                .execute()
        )
        registro_id = reg_result.data[0]['id']

        embed = self.generar_embed(tipo, nombre_contenido, fecha, lugar, puestos, participantes, link_build=link_build)
        msg = await ctx.send(content=f"🔔 {rol.mention if rol else '@here'} ¡Inscripciones!", embed=embed)

        hilo = await msg.create_thread(name=f"Inscripción - {nombre_contenido}")
        await hilo.send("📢 Escribe el **número** para anotarte o **-número** para salir.")

        await asyncio.to_thread(
            lambda: get_db().table('registros_activos')
                .insert({
                    'hilo_id': str(hilo.id),
                    'registro_actividad_id': registro_id,
                    'guild_id': str(ctx.guild.id),
                    'tipo': tipo,
                    'nombre_contenido': nombre_contenido,
                    'fecha_actividad': fecha,
                    'lugar': lugar,
                    'link_build': link_build,
                    'multiplicador': multiplicador,
                    'msg_id': msg.id,
                    'puestos_nombres': puestos,
                    'participantes': participantes
                })
                .execute()
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, discord.Thread):
            return

        hilo_id = str(message.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos')
                .select('*')
                .eq('hilo_id', hilo_id)
                .execute()
        )
        if not result.data:
            await self.bot.process_commands(message)
            return

        act = result.data[0]
        contenido = message.content.strip()
        user_id = str(message.author.id)
        participantes = act['participantes']

        if contenido.isdigit():
            num = contenido
            if num in participantes:
                dueno = participantes[num]
                if dueno and dueno != user_id:
                    try: await message.delete()
                    except: pass
                    await self.bot.process_commands(message)
                    return

                for p in participantes:
                    if participantes[p] == user_id:
                        participantes[p] = None

                participantes[num] = user_id
                await asyncio.to_thread(
                    lambda: get_db().table('registros_activos')
                        .update({'participantes': participantes})
                        .eq('hilo_id', hilo_id)
                        .execute()
                )
                try: await message.delete()
                except: pass
                await self.actualizar_mensaje(message.channel, act)

        elif contenido.startswith("-") and contenido[1:].isdigit():
            num = contenido[1:]
            if participantes.get(num) == user_id:
                participantes[num] = None
                await asyncio.to_thread(
                    lambda: get_db().table('registros_activos')
                        .update({'participantes': participantes})
                        .eq('hilo_id', hilo_id)
                        .execute()
                )
                try: await message.delete()
                except: pass
                await self.actualizar_mensaje(message.channel, act)

        await self.bot.process_commands(message)

    def generar_embed(self, tipo, nombre_contenido, fecha, lugar, nombres, participantes, estado="abierta", motivo=None, link_build=None):
        if estado == "finalizada":
            color, titulo = discord.Color.blue(), f"✅ {nombre_contenido.upper()} - COMPLETADA"
        elif estado == "cancelada":
            color, titulo = discord.Color.red(), f"🚫 {nombre_contenido.upper()} - CANCELADA"
        else:
            color, titulo = discord.Color.green(), f"⚔️ {nombre_contenido.upper()}"

        desc = f"🏷️ **Plantilla:** {tipo.upper()}\n⏰ **Fecha:** {fecha}\n📍 **Lugar:** {lugar}\n"
        if link_build:
            desc += f"🔗 **Builds Requeridas:** {link_build}\n"
        desc += "\n"

        for i, nombre in enumerate(nombres, 1):
            user_id = participantes.get(str(i))
            desc += f"**({i}) {nombre}**: {f'<@{user_id}>' if user_id else '---'}\n"

        embed = discord.Embed(title=titulo, description=desc, color=color)
        if estado == "cancelada" and motivo:
            embed.add_field(name="Razón", value=f"*{motivo}*")
        if estado != "abierta":
            embed.set_footer(text="Actividad cerrada.")
        return embed

    async def actualizar_mensaje(self, hilo, act, estado="abierta", motivo=None):
        try:
            parent_msg = await hilo.parent.fetch_message(int(act['msg_id']))
            nombre_cont = act.get('nombre_contenido') or act['tipo']
            link_build = act.get('link_build')
            nuevo_embed = self.generar_embed(
                act['tipo'], nombre_cont, act['fecha_actividad'], act['lugar'],
                act['puestos_nombres'], act['participantes'], estado, motivo, link_build
            )
            await parent_msg.edit(embed=nuevo_embed)
        except Exception as e:
            print(f"⚠️ Error al actualizar mensaje de actividad: {e}")

    # --- COMANDOS DE GESTIÓN DE ACTIVIDAD ---

    @commands.hybrid_command(name="editar_actividad", description="Modifica lugar o fecha de una actividad activa")
    @app_commands.describe(lugar="Nuevo mapa/zona", fecha="Nueva hora/día")
    @commands.has_any_role("Oficial", "Guild Master")
    async def editar_actividad(self, ctx, lugar: str = None, fecha: str = None):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo.", delete_after=5)

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay actividad activa aquí.", delete_after=5)

        act = result.data[0]
        updates = {}
        if lugar:
            act['lugar'] = lugar
            updates['lugar'] = lugar
        if fecha:
            act['fecha_actividad'] = fecha
            updates['fecha_actividad'] = fecha

        if updates:
            await asyncio.to_thread(
                lambda: get_db().table('registros_activos')
                    .update(updates)
                    .eq('hilo_id', hilo_id)
                    .execute()
            )
        await self.actualizar_mensaje(ctx.channel, act)
        await ctx.send("✅ Información actualizada.", delete_after=5)

    @commands.hybrid_command(name="start", description="Avisa a todos los anotados que es hora de conectar")
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def start(self, ctx):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo.", delete_after=5)

        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('participantes').eq('hilo_id', str(ctx.channel.id)).execute()
        )
        if not result.data or not result.data[0].get('participantes'):
            return await ctx.send("❌ No hay nadie anotado.")

        participantes = result.data[0]['participantes']
        menciones = [f"<@{uid}>" for uid in participantes.values() if uid]
        if not menciones:
            return await ctx.send("❌ Sin participantes.")
        await ctx.send(f"🚀 **¡ATENCIÓN!**\n\n{' '.join(menciones)}\n\n✨ **¡A conectar!** ✨")

    @commands.hybrid_command(name="end", description="Cierra definitivamente una actividad sin repartir silver")
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def end(self, ctx):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)

        await ctx.defer()
        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No se encontró ninguna actividad activa en este hilo.", delete_after=5)

        act = result.data[0]
        await self.actualizar_mensaje(ctx.channel, act, estado="finalizada")
        await asyncio.to_thread(
            lambda: get_db().table('registros_activos').delete().eq('hilo_id', hilo_id).execute()
        )
        await ctx.send("🏁 **Actividad finalizada por el Staff.** Cerrando inscripciones y archivando hilo.")
        await ctx.channel.edit(locked=True, archived=True)

    @commands.hybrid_command(name="anotar", description="Anota a un miembro manualmente en una posición")
    @app_commands.describe(usuario="El miembro a anotar", numero="Número de la posición (ej: 1)")
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def anotar(self, ctx, usuario: discord.Member, numero: str):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay actividad activa en este hilo.", delete_after=5)

        act = result.data[0]
        participantes = act['participantes']
        user_id = str(usuario.id)

        if numero in participantes:
            for p in participantes:
                if participantes[p] == user_id:
                    participantes[p] = None
            participantes[numero] = user_id
            await asyncio.to_thread(
                lambda: get_db().table('registros_activos')
                    .update({'participantes': participantes})
                    .eq('hilo_id', hilo_id)
                    .execute()
            )
            await self.actualizar_mensaje(ctx.channel, act)
            await ctx.send(f"✅ **{usuario.display_name}** anotado en la posición **{numero}**.", delete_after=10)
        else:
            await ctx.send(f"❌ El número **{numero}** no es válido para esta composición.", delete_after=5)

    @commands.hybrid_command(name="desanotar", description="Libera manualmente una posición")
    @app_commands.describe(numero="Número de la posición a vaciar (ej: 1)")
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def desanotar(self, ctx, numero: str):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay actividad activa en este hilo.", delete_after=5)

        act = result.data[0]
        participantes = act['participantes']

        if numero in participantes:
            if participantes[numero] is None:
                return await ctx.send(f"⚠️ La posición **{numero}** ya está vacía.", delete_after=5)
            participantes[numero] = None
            await asyncio.to_thread(
                lambda: get_db().table('registros_activos')
                    .update({'participantes': participantes})
                    .eq('hilo_id', hilo_id)
                    .execute()
            )
            await self.actualizar_mensaje(ctx.channel, act)
            await ctx.send(f"✅ Se ha liberado la posición **{numero}**.", delete_after=10)
        else:
            await ctx.send(f"❌ El número **{numero}** no es válido para esta composición.", delete_after=5)

    @commands.hybrid_command(name="agregar_cupos", description="Añade ranuras extras de participantes a la actividad en curso")
    @app_commands.describe(cantidad="Cuántos cupos extras quieres abrir (ej: 5)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def agregar_cupos(self, ctx, cantidad: int):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)
        if cantidad <= 0:
            return await ctx.send("❌ La cantidad de cupos debe ser mayor a 0.", delete_after=5)

        await ctx.defer()
        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos').select('*').eq('hilo_id', hilo_id).execute()
        )
        if not result.data:
            return await ctx.send("❌ No hay ninguna actividad activa en este hilo.", delete_after=5)

        act = result.data[0]
        participantes = act['participantes']
        numeros_existentes = [int(k) for k in participantes.keys() if k.isdigit()]
        ultimo_numero = max(numeros_existentes) if numeros_existentes else 0

        nuevos_puestos = []
        for i in range(1, cantidad + 1):
            nuevo_indice = str(ultimo_numero + i)
            participantes[nuevo_indice] = None
            nuevos_puestos.append(nuevo_indice)

        await asyncio.to_thread(
            lambda: get_db().table('registros_activos')
                .update({'participantes': participantes})
                .eq('hilo_id', hilo_id)
                .execute()
        )
        await self.actualizar_mensaje(ctx.channel, act)

        embed_agregados = discord.Embed(
            title="➕ ¡CUPOS EXTRAS AÑADIDOS!",
            description=f"Se expandió la composición en **{cantidad} slots nuevos**.",
            color=discord.Color.orange()
        )
        lista_texto = "\n".join(f"**({num}) {act['tipo'].upper()}** — Vacante" for num in nuevos_puestos)
        embed_agregados.add_field(
            name=f"📋 Slots habilitados (del {nuevos_puestos[0]} al {nuevos_puestos[-1]})",
            value=lista_texto,
            inline=False
        )
        embed_agregados.set_footer(text="¡Inscripciones abiertas!")
        await ctx.send(embed=embed_agregados)


async def setup(bot):
    await bot.add_cog(PingsAlbion(bot))

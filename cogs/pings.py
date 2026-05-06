import discord
from discord.ext import commands
import asyncio
import json
import os

class PingsAlbion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.archivo_data = "actividades.json"
        if not os.path.exists(self.archivo_data):
            with open(self.archivo_data, "w") as f:
                json.dump({}, f)

    def cargar_datos(self):
        with open(self.archivo_data, "r") as f:
            return json.load(f)

    def guardar_datos(self, data):
        with open(self.archivo_data, "w") as f:
            json.dump(data, f, indent=4)

    @commands.command(name="crear_plantilla")
    @commands.has_permissions(administrator=True)
    async def crear_plantilla(self, ctx, nombre: str, *, puestos_str: str):
        try: await ctx.message.delete()
        except: pass
        data = self.cargar_datos()
        lista_puestos = [p.strip() for p in puestos_str.split(",")]
        data[nombre.lower()] = lista_puestos
        self.guardar_datos(data)
        await ctx.send(f"✅ Plantilla **{nombre}** creada.", delete_after=5)

    @commands.command(name="ping")
    @commands.has_permissions(manage_messages=True)
    async def ping_dinamico(self, ctx, tipo: str, rol_ping: discord.Role = None, id_mensaje_build: str = None, *, info: str = "Sin detalles adicionales"):
        try: await ctx.message.delete()
        except: pass

        data = self.cargar_datos()
        tipo_buscado = tipo.lower()

        if tipo_buscado not in data:
            await ctx.send(f"❌ La actividad `{tipo}` no existe.", delete_after=5)
            return

        puestos_nombres = data[tipo_buscado]
        participantes = {i+1: None for i in range(len(puestos_nombres))}
        
        url_imagen = None
        if id_mensaje_build and id_mensaje_build.isdigit():
            try:
                canal_builds = discord.utils.get(ctx.guild.text_channels, name="builds") or ctx.channel
                msg_build = await canal_builds.fetch_message(int(id_mensaje_build))
                if msg_build.attachments:
                    url_imagen = msg_build.attachments[0].url
            except: pass

        def generar_embed():
            desc = ""
            for i, nombre in enumerate(puestos_nombres, 1):
                user = participantes[i]
                mencion = user.mention if user else "---"
                desc += f"**({i}) {nombre}**: {mencion}\n"
            
            embed = discord.Embed(title=f"⚔️ {tipo.upper()}", description=desc, color=discord.Color.green())
            embed.add_field(name="Información", value=info)
            if url_imagen:
                embed.set_image(url=url_imagen)
            return embed

        rol_miembro = discord.utils.get(ctx.guild.roles, name="Miembro")
        mencion_final = ""
        if rol_ping: mencion_final += f"{rol_ping.mention} "
        if rol_miembro: mencion_final += f"{rol_miembro.mention}"
        
        msg_lista = await ctx.send(content=mencion_final if mencion_final else None, embed=generar_embed())
        
        hilo = await msg_lista.create_thread(name=f"Inscripción - {tipo}", auto_archive_duration=60)
        await hilo.send("📢 **Utiliza el número solo para registrarte en la actividad | Usa -número para salir**")

        def check(m):
            return m.channel.id == hilo.id and not m.author.bot

        while True:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=7200)
                contenido = msg.content.strip()
                usuario = msg.author

                # --- Lógica para quitarse (-número) ---
                if contenido.startswith("-") and contenido[1:].isdigit():
                    try: await msg.delete()
                    except: pass
                    try:
                        num = int(contenido[1:])
                        if participantes.get(num) == usuario:
                            participantes[num] = None
                            await msg_lista.edit(embed=generar_embed())
                    except: pass
                
                # --- Lógica para anotarse (número) ---
                elif contenido.isdigit():
                    try: await msg.delete()
                    except: pass
                    
                    num = int(contenido)
                    if num in participantes:
                        # VERIFICACIÓN: ¿El puesto ya está ocupado?
                        if participantes[num] is not None:
                            # Evitamos enviarle DM si por algún motivo pone el número de su propio puesto
                            if participantes[num] != usuario:
                                nombre_rol = puestos_nombres[num - 1]
                                dueño_actual = participantes[num].display_name
                                try:
                                    # Intentamos enviar el MD
                                    await usuario.send(f"❌ Intentaste tomar el puesto **{num} ({nombre_rol})**, pero ya está ocupado por **{dueño_actual}**.")
                                except discord.Forbidden:
                                    # Si tiene los MD cerrados, le avisamos por el hilo y borramos el mensaje rápido
                                    await hilo.send(f"❌ {usuario.mention}, el puesto **{nombre_rol}** ya está ocupado por {dueño_actual}.", delete_after=5)
                        else:
                            # El puesto está libre, lo anotamos
                            for p in participantes:
                                if participantes[p] == usuario: participantes[p] = None
                            participantes[num] = usuario
                            await msg_lista.edit(embed=generar_embed())
                    else:
                        await hilo.send(f"❌ El puesto {num} no existe en esta lista.", delete_after=3)

            except asyncio.TimeoutError:
                break

    # --- COMANDO MASS PING ---
    @commands.command(name="mass")
    @commands.has_permissions(manage_messages=True)
    async def mass_ping(self, ctx, *, mensaje_extra: str = "¡Log in ya salimos!"):
        """Pingea a todos los anotados en la lista de este hilo"""
        try: await ctx.message.delete()
        except: pass

        if isinstance(ctx.channel, discord.Thread):
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
                        lista_menciones = " ".join(menciones)
                        await ctx.send(f"📢 {lista_menciones}\n**{mensaje_extra}**")
                    else:
                        await ctx.send("❌ No hay nadie anotado en la lista todavía.", delete_after=5)
            except Exception as e:
                await ctx.send(f"❌ Error al buscar la lista: {e}", delete_after=5)
        else:
            await ctx.send("❌ Este comando solo funciona dentro del hilo de una actividad.", delete_after=5)

async def setup(bot):
    await bot.add_cog(PingsAlbion(bot))
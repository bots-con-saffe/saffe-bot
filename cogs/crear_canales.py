import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from db import get_db


class CrearCanales(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_categorias = {
            "╭✦・𝗕𝗜𝗘𝗡𝗩𝗘𝗡𝗜𝗗𝗔𝗦": {"lobby": "🎤 ︱ Crear Entrevista", "prefijo": "🎤 ︱ Entrevista"},
            "╭✦・𝗚𝗥𝗘𝗠𝗜𝗔𝗟":     {"lobby": "➕ ︱ Crear Chozita",   "prefijo": "🔊 ︱ Chozita"},
            "╭✦・𝗖𝗢𝗡𝗧𝗘𝗡𝗜𝗗𝗢 𝗣𝗩𝗘": {"lobby": "➕ ︱ Crear PvE",     "prefijo": "⚔️ ︱ PvE"},
            "╭✦・𝗖𝗢𝗡𝗧𝗘𝗡𝗜𝗗𝗢 𝗔𝗩𝗔": {"lobby": "➕ ︱ Crear Ava",     "prefijo": "💠 ︱ Ava"},
            "╭✦・𝗦𝗧𝗔𝗙𝗙":        {"lobby": "🔒 ︱ Crear Reunión",  "prefijo": "🔒 ︱ Reunión"},
        }
        self.lobby_ids = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for cat_name, config in self.config_categorias.items():
                category = discord.utils.get(guild.categories, name=cat_name)
                if category:
                    lobby = discord.utils.get(category.voice_channels, name=config["lobby"])
                    if not lobby:
                        try:
                            lobby = await guild.create_voice_channel(config["lobby"], category=category)
                        except: continue
                    self.lobby_ids[lobby.id] = config["prefijo"]

            # Limpiar canales temporales que quedaron del restart anterior
            result = await asyncio.to_thread(
                lambda: get_db().table('canales_temporales')
                    .select('canal_id')
                    .eq('guild_id', str(guild.id))
                    .execute()
            )
            ids_a_quitar = []
            for row in result.data:
                canal = guild.get_channel(int(row['canal_id']))
                if canal:
                    if len(canal.members) == 0:
                        try: await canal.delete()
                        except: pass
                        ids_a_quitar.append(row['canal_id'])
                else:
                    ids_a_quitar.append(row['canal_id'])

            for cid in ids_a_quitar:
                await asyncio.to_thread(
                    lambda c=cid: get_db().table('canales_temporales')
                        .delete()
                        .eq('canal_id', c)
                        .execute()
                )

        print("✅ Canales temporales verificados.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Crear sala temporal
        if after.channel and after.channel.id in self.lobby_ids:
            prefijo = self.lobby_ids[after.channel.id]
            try:
                nuevo = await member.guild.create_voice_channel(
                    name=f"{prefijo} de {member.display_name}",
                    category=after.channel.category
                )
                await asyncio.to_thread(
                    lambda: get_db().table('canales_temporales')
                        .upsert({'canal_id': str(nuevo.id), 'owner_id': str(member.id), 'guild_id': str(member.guild.id)})
                        .execute()
                )
                await nuevo.set_permissions(member, manage_channels=True, manage_permissions=True, connect=True)
                await member.move_to(nuevo)
            except: pass

        # Borrar sala o transferir liderazgo
        if before.channel:
            cid = str(before.channel.id)
            result = await asyncio.to_thread(
                lambda: get_db().table('canales_temporales')
                    .select('owner_id')
                    .eq('canal_id', cid)
                    .execute()
            )
            if result.data:
                owner_id = result.data[0]['owner_id']
                if len(before.channel.members) == 0:
                    try: await before.channel.delete()
                    except: pass
                    await asyncio.to_thread(
                        lambda: get_db().table('canales_temporales')
                            .delete()
                            .eq('canal_id', cid)
                            .execute()
                    )
                elif owner_id == str(member.id):
                    nuevo_dueno = before.channel.members[0]
                    await asyncio.to_thread(
                        lambda: get_db().table('canales_temporales')
                            .update({'owner_id': str(nuevo_dueno.id)})
                            .eq('canal_id', cid)
                            .execute()
                    )
                    await before.channel.set_permissions(nuevo_dueno, manage_channels=True, manage_permissions=True)
                    try:
                        prefijo = "🔊"
                        for cat, config in self.config_categorias.items():
                            if before.channel.category and before.channel.category.name == cat:
                                prefijo = config["prefijo"]
                                break
                        await before.channel.edit(name=f"{prefijo} de {nuevo_dueno.display_name}")
                    except: pass

    async def validar_sala(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ ¡Entra a tu canal primero!", delete_after=5)
            if ctx.interaction is None:
                try: await ctx.message.delete(delay=5)
                except: pass
            return None

        cid = str(ctx.author.voice.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('canales_temporales')
                .select('owner_id')
                .eq('canal_id', cid)
                .execute()
        )
        if not result.data or result.data[0]['owner_id'] != str(ctx.author.id):
            await ctx.send("❌ No eres el líder de esta sala.", delete_after=5)
            if ctx.interaction is None:
                try: await ctx.message.delete(delay=5)
                except: pass
            return None

        return ctx.author.voice.channel

    @commands.hybrid_command(name="name", description="Cambia el nombre de tu sala")
    @app_commands.describe(nuevo_nombre="Nuevo nombre para la sala")
    async def name(self, ctx, *, nuevo_nombre: str):
        canal = await self.validar_sala(ctx)
        if canal:
            try:
                await canal.edit(name=nuevo_nombre)
                await ctx.send(f"✅ Nombre cambiado: **{nuevo_nombre}**", delete_after=5)
                if ctx.interaction is None:
                    try: await ctx.message.delete(delay=1)
                    except: pass
            except:
                await ctx.send("⚠️ Límite de Discord: No cambies el nombre tan rápido.", delete_after=5)

    @commands.hybrid_command(name="limite", description="Establece el límite de usuarios de tu sala")
    @app_commands.describe(num="Número máximo de usuarios (0 = sin límite)")
    async def limite(self, ctx, num: int):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.edit(user_limit=num)
            limite_str = str(num) if num > 0 else "sin límite"
            await ctx.send(f"✅ Límite: {limite_str}", delete_after=5)

    @commands.hybrid_command(name="lock", description="Bloquea tu sala")
    async def lock(self, ctx):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.set_permissions(ctx.guild.default_role, connect=False)
            await ctx.send("🔒 Sala bloqueada.", delete_after=5)
            if ctx.interaction is None:
                try: await ctx.message.delete(delay=1)
                except: pass

    @commands.hybrid_command(name="unlock", description="Abre tu sala")
    async def unlock(self, ctx):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.set_permissions(ctx.guild.default_role, connect=None)
            await ctx.send("🔓 Sala abierta.", delete_after=5)
            if ctx.interaction is None:
                try: await ctx.message.delete(delay=1)
                except: pass


async def setup(bot):
    await bot.add_cog(CrearCanales(bot))

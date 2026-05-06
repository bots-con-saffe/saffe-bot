import discord
from discord.ext import commands
from discord import app_commands


class CrearCanales(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_categorias = {
            "Contenido PVE": {"lobby": "⚔️ Únete para PVE", "prefijo": "⚔️ PvE"},
            "Contenido PVP": {"lobby": "🔴 Únete para PVP", "prefijo": "🔴 PvP"},
            "Avalonianas":   {"lobby": "💎 Únete para Ava", "prefijo": "💎 Ava"}
        }
        self.lobby_ids = {}
        self.salas_temporales = {}  # canal_id -> owner_id

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for cat_name, config in self.config_categorias.items():
                category = discord.utils.get(guild.categories, name=cat_name)
                if category:
                    lobby = discord.utils.get(category.voice_channels, name=config["lobby"])
                    if not lobby:
                        lobby = await guild.create_voice_channel(config["lobby"], category=category)
                    self.lobby_ids[lobby.id] = config["prefijo"]
        print("✅ Mini-lobbies verificadas.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Creación de sala temporal
        if after.channel and after.channel.id in self.lobby_ids:
            prefijo = self.lobby_ids[after.channel.id]
            nuevo_canal = await member.guild.create_voice_channel(
                name=f"{prefijo} de {member.display_name}",
                category=after.channel.category
            )
            self.salas_temporales[nuevo_canal.id] = member.id
            await nuevo_canal.set_permissions(member, manage_channels=True, manage_permissions=True)
            await member.move_to(nuevo_canal)

        # Limpieza y cambio de líder
        if before.channel and before.channel.id in self.salas_temporales:
            if len(before.channel.members) == 0:
                del self.salas_temporales[before.channel.id]
                await before.channel.delete()
            else:
                if self.salas_temporales[before.channel.id] == member.id:
                    nuevo_dueno = before.channel.members[0]
                    self.salas_temporales[before.channel.id] = nuevo_dueno.id
                    await before.channel.set_permissions(nuevo_dueno, manage_channels=True, manage_permissions=True)
                    await before.channel.send(
                        f"👑 **{nuevo_dueno.display_name}** es el nuevo líder.",
                        delete_after=10
                    )

    async def validar_sala(self, ctx):
        try:
            await ctx.message.delete()
        except: pass

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ ¡Debes estar en una sala de voz!", delete_after=5)
            return None

        canal_id = ctx.author.voice.channel.id
        if canal_id not in self.salas_temporales:
            await ctx.send("❌ Esta no es una sala temporal controlada por el bot.", delete_after=5)
            return None

        if self.salas_temporales[canal_id] != ctx.author.id:
            await ctx.send("❌ No eres el líder actual de esta sala.", delete_after=5)
            return None

        return ctx.author.voice.channel

    @commands.hybrid_command(name="name", description="Cambia el nombre de tu sala de voz temporal")
    @app_commands.describe(nuevo_nombre="Nuevo nombre para la sala")
    async def name(self, ctx, *, nuevo_nombre: str):
        canal = await self.validar_sala(ctx)
        if canal:
            try:
                await canal.edit(name=nuevo_nombre)
                await ctx.send(f"✅ Nombre cambiado a: **{nuevo_nombre}**", delete_after=5)
            except discord.HTTPException:
                await ctx.send("⚠️ Límite de Discord: Solo 2 cambios de nombre cada 10 min.", delete_after=10)

    @commands.hybrid_command(name="limite", description="Establece el límite de usuarios de tu sala")
    @app_commands.describe(num="Número máximo de usuarios (0 = sin límite)")
    async def limite(self, ctx, num: int):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.edit(user_limit=num)
            limite_str = str(num) if num > 0 else "sin límite"
            await ctx.send(f"✅ Límite: {limite_str}", delete_after=5)

    @commands.hybrid_command(name="lock", description="Bloquea tu sala para que nadie más pueda entrar")
    async def lock(self, ctx):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.set_permissions(ctx.guild.default_role, connect=False)
            await ctx.send("🔒 Sala bloqueada.", delete_after=5)

    @commands.hybrid_command(name="unlock", description="Abre tu sala al público")
    async def unlock(self, ctx):
        canal = await self.validar_sala(ctx)
        if canal:
            await canal.set_permissions(ctx.guild.default_role, connect=None)
            await ctx.send("🔓 Sala abierta.", delete_after=5)


async def setup(bot):
    await bot.add_cog(CrearCanales(bot))

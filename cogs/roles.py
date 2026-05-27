import discord
from discord.ext import commands
from discord import app_commands


class AsignacionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.PAQUETES = {
            "miembro": ["Miembro", "PvE Content", "PvP Content"],
            "miembroava": ["Miembro", "PvE Content", "PvP Content", "Ava Core"]
        }

    async def paquete_autocomplete(self, interaction: discord.Interaction, current: str):
        opciones = list(self.PAQUETES.keys())
        return [
            app_commands.Choice(name=opc, value=opc)
            for opc in opciones if current.lower() in opc.lower()
        ]

    @commands.hybrid_command(name="rol", description="Asigna roles de golpe a un nuevo integrante")
    @app_commands.describe(paquete="miembro o miembroava", usuario="El miembro a rankear")
    @app_commands.autocomplete(paquete=paquete_autocomplete)
    @commands.has_any_role("Oficial", "Guild Master")
    async def rol(self, ctx, paquete: str, usuario: discord.Member):
        paquete = paquete.lower()
        if paquete not in self.PAQUETES:
            return await ctx.send(f"❌ Paquete inválido. Usa: `miembro` o `miembroava`", delete_after=5)

        roles_a_dar = []
        for nombre in self.PAQUETES[paquete]:
            r = discord.utils.get(ctx.guild.roles, name=nombre)
            if r:
                roles_a_dar.append(r)

        if roles_a_dar:
            try:
                await usuario.add_roles(*roles_a_dar)
                scout = discord.utils.get(ctx.guild.roles, name="Scout")
                if scout and scout in usuario.roles:
                    await usuario.remove_roles(scout)
                await ctx.send(f"✅ Se han asignado los roles de **{paquete}** a {usuario.mention}.", delete_after=10)
            except discord.Forbidden:
                await ctx.send("❌ Error: Verifica que el rol del bot esté arriba de los demás.")


async def setup(bot):
    await bot.add_cog(AsignacionRoles(bot))

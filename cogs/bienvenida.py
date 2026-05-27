import discord
from discord.ext import commands
from discord import app_commands


class Bienvenida(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # 1. Asignación del rol Scout
        rol = discord.utils.get(member.guild.roles, name="Scout")
        if rol:
            try:
                await member.add_roles(rol)
                print(f"✅ Se asignó el rol 'Scout' a {member.display_name}")
            except discord.Forbidden:
                print(f"⚠️ Error 403: El bot no tiene permisos para dar el rol 'Scout'.")
        else:
            print("❌ No se encontró ningún rol llamado 'Scout'.")

        # 2. Mensaje de bienvenida en #ingresos
        canal_ingresos = None
        for canal in member.guild.text_channels:
            if "ingresos" in canal.name.lower():
                canal_ingresos = canal
                break

        if canal_ingresos:
            mensaje = (
                f"Hey {member.mention} ¡Bienvenido! 👋\n\n"
                "Léete las **reglas** y **anuncios**. Si te interesa unirte a nosotros, "
                "pasa al canal de **registro** y luego **crea un ticket** para que nuestros "
                "oficiales te atiendan. ⚔️"
            )
            try:
                await canal_ingresos.send(mensaje)
            except discord.Forbidden:
                print(f"⚠️ Error: Sin permisos para escribir en {canal_ingresos.name}.")
        else:
            print("❌ No se encontró el canal de ingresos para el saludo.")

    @commands.hybrid_command(name="test_scout", description="Prueba el rol Scout y el mensaje de bienvenida")
    async def test_scout(self, ctx):
        """Simula la entrada para probar que el rol y el mensaje funcionan."""
        rol = discord.utils.get(ctx.guild.roles, name="Scout")
        if rol:
            try:
                await ctx.author.remove_roles(rol)
                await self.on_member_join(ctx.author)
                await ctx.send("✅ Simulación completada: Revisa el canal de ingresos.", delete_after=5)
            except discord.Forbidden:
                await ctx.send(
                    "⚠️ Error 403: Sube el rol del bot por encima de 'Scout' en los ajustes del servidor.",
                    delete_after=10
                )
        else:
            await ctx.send("❌ No se encontró el rol 'Scout'.", delete_after=5)


async def setup(bot):
    await bot.add_cog(Bienvenida(bot))

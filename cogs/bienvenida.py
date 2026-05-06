import discord
from discord.ext import commands
from discord import app_commands


class Bienvenida(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        nombre_rol = "Scout"
        rol = discord.utils.get(member.guild.roles, name=nombre_rol)

        if rol:
            try:
                await member.add_roles(rol)
                print(f"✅ Se asignó el rol '{nombre_rol}' a {member.display_name}")
            except discord.Forbidden:
                print(f"⚠️ Error 403: El bot no tiene permisos para dar el rol '{nombre_rol}'.")
        else:
            print(f"❌ No se encontró ningún rol llamado '{nombre_rol}'.")

    @commands.hybrid_command(name="test_scout", description="Simula la entrada de un nuevo miembro para probar la asignación del rol Scout")
    async def test_scout(self, ctx):
        nombre_rol = "Scout"
        rol = discord.utils.get(ctx.guild.roles, name=nombre_rol)

        if rol:
            try:
                await ctx.author.remove_roles(rol)
                await ctx.author.add_roles(rol)
                await ctx.send("✅ ¡Simulación exitosa! Se te ha dado el rol Scout.", delete_after=5)
            except discord.Forbidden:
                await ctx.send(
                    "⚠️ Error 403: El bot no tiene permiso. Pon el rol del bot por encima del rol Scout en los ajustes del servidor.",
                    delete_after=10
                )
        else:
            await ctx.send(f"❌ No se encontró el rol '{nombre_rol}'.", delete_after=5)


async def setup(bot):
    await bot.add_cog(Bienvenida(bot))

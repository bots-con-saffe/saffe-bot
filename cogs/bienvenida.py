import discord
from discord.ext import commands

# Creamos una clase que hereda de commands.Cog
class Bienvenida(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # En los Cogs, los eventos usan el decorador @commands.Cog.listener()
    @commands.Cog.listener()
    async def on_member_join(self, member):
        nombre_rol = "Scout" 
        rol = discord.utils.get(member.guild.roles, name=nombre_rol)
        
        if rol:
            try:
                await member.add_roles(rol)
                print(f"✅ Se asignó el rol '{nombre_rol}' a {member.display_name}")
            except discord.Forbidden:
                print(f"⚠️ Error 403: El bot no tiene permisos para dar el rol.")
        else:
            print(f"❌ No se encontró ningún rol llamado '{nombre_rol}'.")
    # ... (tu código de on_member_join arriba) ...

    # Comando temporal para probar la asignación de rol
    @commands.command()
    async def test_scout(self, ctx):
        nombre_rol = "Scout"
        rol = discord.utils.get(ctx.guild.roles, name=nombre_rol)
        
        if rol:
            try:
                # Quitamos el rol primero (por si ya lo tienes) para probar bien
                await ctx.author.remove_roles(rol)
                # Volvemos a asignarlo simulando que acabas de entrar
                await ctx.author.add_roles(rol)
                await ctx.send("✅ ¡Simulación exitosa! Se te ha dado el rol Scout.")
            except discord.Forbidden:
                await ctx.send("⚠️ Error 403: El bot no tiene permiso. Recuerda poner el rol del bot por encima del rol Scout en los ajustes del servidor.")
        else:
            await ctx.send(f"❌ No se encontró el rol '{nombre_rol}'.")
# Esta función es obligatoria al final del archivo para que el bot pueda "cargar" este código
async def setup(bot):
    await bot.add_cog(Bienvenida(bot))
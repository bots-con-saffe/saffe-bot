import discord
from discord.ext import commands
from discord import app_commands


class AsignacionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    PAQUETES = {
        "miembro": ["Miembro", "Pve content", "Pvp content"],
        "miembroava": ["Miembro", "Pve content", "Pvp content", "Ava core"]
    }

    @commands.hybrid_command(name="rol", description="Asigna un paquete de roles a un miembro")
    @app_commands.describe(
        paquete="Paquete de roles a asignar (miembro / miembroava)",
        usuario="Miembro al que se le asignan los roles"
    )
    @commands.has_permissions(manage_roles=True)
    async def asignar_paquete(self, ctx, paquete: str, usuario: discord.Member):
        await ctx.defer(ephemeral=True)
        try:
            await ctx.message.delete()
        except: pass

        paquete = paquete.lower()

        if paquete not in self.PAQUETES:
            opciones = ", ".join(self.PAQUETES.keys())
            await ctx.send(f"❌ Paquete no encontrado. Opciones: `{opciones}`", delete_after=5)
            return

        nombres_roles = self.PAQUETES[paquete]
        roles_a_agregar = []
        roles_no_encontrados = []

        for nombre in nombres_roles:
            rol = discord.utils.get(ctx.guild.roles, name=nombre)
            if rol:
                roles_a_agregar.append(rol)
            else:
                roles_no_encontrados.append(nombre)

        if roles_no_encontrados:
            nombres_faltantes = ", ".join(roles_no_encontrados)
            await ctx.send(f"⚠️ No encontré estos roles en el servidor: **{nombres_faltantes}**.", delete_after=7)

        if roles_a_agregar:
            try:
                await usuario.add_roles(*roles_a_agregar)
                await ctx.send(
                    f"✅ Roles del paquete **{paquete.capitalize()}** dados a {usuario.mention}.",
                    delete_after=5
                )
            except discord.Forbidden:
                await ctx.send(
                    "❌ Error 403: No tengo permisos. Pon mi rol por encima de los que asigno.",
                    delete_after=5
                )

    @asignar_paquete.error
    async def rol_error(self, ctx, error):
        try:
            await ctx.message.delete()
        except: pass

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Uso incorrecto. Ejemplo: `!rol miembro @usuario`", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ No pude encontrar a ese usuario. Menciónalo con `@`.", delete_after=5)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ No tienes permiso para gestionar roles.", delete_after=5)


async def setup(bot):
    await bot.add_cog(AsignacionRoles(bot))

import discord
from discord.ext import commands

class AsignacionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="rol")
    @commands.has_permissions(manage_roles=True)
    async def asignar_paquete(self, ctx, paquete: str, usuario: discord.Member):
        # 1. Borramos tu mensaje "!rol ..." instantáneamente
        try:
            await ctx.message.delete()
        except: pass

        paquete = paquete.lower()
        
        # 2. Los paquetes de roles
        paquetes = {
            "miembro": ["Miembro", "Pve content", "Pvp content"],
            "miembroava": ["Miembro", "Pve content", "Pvp content", "Ava core"]
        }

        # 3. Verificaciones
        if paquete not in paquetes:
            opciones = ", ".join(paquetes.keys())
            await ctx.send(f"❌ Paquete no encontrado. Opciones: `{opciones}`", delete_after=5)
            return

        nombres_roles = paquetes[paquete]
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
            await ctx.send(f"⚠️ Me faltaron estos roles: **{nombres_faltantes}**.", delete_after=7)

        # 4. Asignar roles y avisar
        if roles_a_agregar:
            try:
                await usuario.add_roles(*roles_a_agregar)
                await ctx.send(f"✅ Roles del paquete **{paquete.capitalize()}** dados a {usuario.mention}.", delete_after=3)
            except discord.Forbidden:
                await ctx.send("❌ Error 403: No tengo permisos. Pon mi rol por encima de los que asigno.", delete_after=5)

    # Manejo de errores con limpieza
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
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
from db import get_db


class Moderacion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="clear", description="Borra los últimos N mensajes (respeta los anclados)")
    @app_commands.describe(cantidad="Número de mensajes a borrar (por defecto 5)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def clear(self, ctx, cantidad: int = 5):
        await ctx.defer(ephemeral=True)
        borrados = await ctx.channel.purge(limit=cantidad, check=lambda msg: not msg.pinned)
        msg = f"✅ Se han borrado **{len(borrados)}** mensajes. (Los anclados se mantuvieron)"
        if ctx.interaction:
            await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.send(msg, delete_after=3)

    @commands.hybrid_command(name="callout", description="Cancela la actividad activa del hilo")
    @app_commands.describe(motivo="Razón de la cancelación")
    @commands.has_any_role("Oficial", "Guild Master", "Creador de Contenido")
    async def callout(self, ctx, motivo: str):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto en un hilo.")

        hilo_id = str(ctx.channel.id)
        result = await asyncio.to_thread(
            lambda: get_db().table('registros_activos')
                .select('*')
                .eq('hilo_id', hilo_id)
                .execute()
        )

        if not result.data:
            return await ctx.send("❌ No hay registro activo aquí.")

        registro = result.data[0]
        pings_cog = self.bot.get_cog("PingsAlbion")
        if pings_cog:
            await pings_cog.actualizar_mensaje(ctx.channel, registro, estado="cancelada", motivo=motivo)

        await asyncio.to_thread(
            lambda: get_db().table('registros_activos')
                .delete()
                .eq('hilo_id', hilo_id)
                .execute()
        )
        await ctx.send(f"🚫 Actividad cancelada: **{motivo}**.")

    @commands.hybrid_command(name="kick_gremio", description="Remueve todos los roles de un miembro y lo expulsa del Discord")
    @app_commands.describe(usuario="El miembro a expulsar", motivo="Razón de la expulsión")
    @commands.has_any_role("Oficial", "Guild Master")
    async def kick_gremio(self, ctx, usuario: discord.Member, *, motivo: str = "Limpieza de inactivos / Decisión del Staff"):
        await ctx.defer()

        if usuario.id == ctx.author.id:
            return await ctx.send("❌ No puedes expulsarte a ti mismo.")
        if usuario.id == ctx.guild.owner_id:
            return await ctx.send("❌ No puedes expulsar al dueño del servidor.")

        nombre_usuario = usuario.display_name
        menciones_roles = [rol.mention for rol in usuario.roles if rol != ctx.guild.default_role]
        roles_a_quitar = [rol for rol in usuario.roles if rol != ctx.guild.default_role]

        if roles_a_quitar:
            try:
                await usuario.remove_roles(*roles_a_quitar, reason=f"Remoción previa a expulsión - Ejecutado por {ctx.author.display_name}")
            except discord.Forbidden:
                return await ctx.send("⚠️ Error: El bot no tiene permisos suficientes para quitar los roles de este usuario. Revisa la jerarquía de roles.")

        try:
            embed_dm = discord.Embed(
                title="⚔️ Notificación de Gremio ⚔️",
                description=f"Has sido expulsado del gremio.\n\n**Razón:** {motivo}",
                color=discord.Color.red()
            )
            await usuario.send(embed=embed_dm)
        except: pass

        try:
            await usuario.kick(reason=f"Ejecutado por {ctx.author.display_name}. Motivo: {motivo}")

            embed_publico = discord.Embed(
                title="🥾 MIEMBRO EXPULSADO 🥾",
                description=f"El Staff ha removido a **{nombre_usuario}** del servidor.",
                color=discord.Color.dark_orange()
            )
            embed_publico.add_field(name="👤 Expulsado:", value=f"**{nombre_usuario}** (ID: `{usuario.id}`)", inline=True)
            embed_publico.add_field(name="🛡️ Ejecutado por:", value=ctx.author.mention, inline=True)
            embed_publico.add_field(name="📄 Motivo declarado:", value=f"*{motivo}*", inline=False)
            embed_publico.add_field(
                name="🗑️ Roles purgados:",
                value=", ".join(menciones_roles) if menciones_roles else "Ninguno",
                inline=False
            )
            await ctx.send(embed=embed_publico)

        except discord.Forbidden:
            await ctx.send("⚠️ Error: El bot no tiene el permiso de 'Expulsar Miembros' o el rol del usuario es más alto que el del bot.")
        except Exception as e:
            await ctx.send(f"❌ Ocurrió un error inesperado al intentar expulsar al miembro:\n```py\n{e}\n```")

    @commands.hybrid_command(name="kick", description="Expulsa a un miembro del servidor")
    @app_commands.describe(member="Miembro a expulsar", razon="Motivo de la expulsión")
    @commands.has_any_role("Oficial", "Guild Master")
    async def kick_user(self, ctx, member: discord.Member, *, razon: str = "No especificada"):
        view = ConfirmacionMod(member, "expulsar", razon)
        await ctx.send(
            f"⚠️ {ctx.author.mention}, ¿confirmas **expulsar** a {member.mention}?\nMotivo: {razon}",
            view=view
        )

    @commands.hybrid_command(name="timeout", description="Silencia a un miembro durante N minutos")
    @app_commands.describe(member="Miembro a silenciar", minutos="Duración en minutos", razon="Motivo del silencio")
    @commands.has_any_role("Oficial", "Guild Master")
    async def timeout_user(self, ctx, member: discord.Member, minutos: int, *, razon: str = "No especificada"):
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("⚠️ El bot no tiene permiso de 'Moderar miembros'.", delete_after=10)

        roles_protegidos = ["Oficial", "Guild Master"]
        if any(r.name in roles_protegidos for r in member.roles):
            return await ctx.send(f"❌ No se puede silenciar a **{member.display_name}** porque tiene un rol protegido.", delete_after=10)

        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ No puedo silenciar a este usuario (su rango es igual o mayor al mío).", delete_after=10)

        view = ConfirmacionMod(member, "silenciar", razon, minutos)
        await ctx.send(
            f"⚖️ **SOLICITUD DE TIMEOUT**\n"
            f"**Usuario:** {member.mention}\n"
            f"**Duración:** {minutos} minutos\n"
            f"**Razón:** {razon}\n\n"
            f"¿Confirmas esta acción, {ctx.author.mention}?",
            view=view
        )

    @timeout_user.error
    async def timeout_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Falta información. Uso: `!timeout @usuario minutos motivo`", delete_after=10)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Error en los datos. ¿Pusiste el número de minutos correctamente?", delete_after=10)
        elif isinstance(error, commands.MissingAnyRole):
            await ctx.send("❌ No tienes los roles necesarios (Oficial o Guild Master).", delete_after=10)
        else:
            print(f"Error en !timeout: {error}")


class ConfirmacionMod(discord.ui.View):
    def __init__(self, target, accion, razon, tiempo=None):
        super().__init__(timeout=30)
        self.target = target
        self.accion = accion
        self.razon = razon
        self.tiempo = tiempo

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.name in ["Oficial", "Guild Master"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ No tienes permiso para confirmar.", ephemeral=True)
        try:
            if self.accion == "expulsar":
                await self.target.kick(reason=self.razon)
                await interaction.response.edit_message(content=f"✅ **{self.target.display_name}** expulsado.", view=None)
            elif self.accion == "silenciar":
                duracion = datetime.timedelta(minutes=self.tiempo)
                await self.target.timeout(duracion, reason=self.razon)
                await interaction.response.edit_message(content=f"✅ **{self.target.display_name}** silenciado por {self.tiempo} minutos.", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error técnico: {e}", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Acción cancelada.", view=None)


async def setup(bot):
    await bot.add_cog(Moderacion(bot))

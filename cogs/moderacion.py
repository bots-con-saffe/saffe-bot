import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
from db import get_db


class Moderacion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="clear", aliases=["borrar", "limpiar"], description="Borra los últimos N mensajes del canal")
    @app_commands.describe(cantidad="Número de mensajes a borrar (por defecto 5)")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, cantidad: int = 5):
        await ctx.defer(ephemeral=True)
        borrados = await ctx.channel.purge(limit=cantidad)
        await ctx.send(f"✅ Se han borrado **{len(borrados)}** mensajes.", delete_after=3)

    @commands.hybrid_command(name="callout", description="Cierra la actividad: registra asistencias y archiva el hilo")
    @commands.has_any_role("Oficial", "Guild Master")
    async def callout(self, ctx):
        await ctx.defer()
        try:
            await ctx.message.delete()
        except: pass

        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)

        try:
            parent_msg = await ctx.channel.parent.fetch_message(ctx.channel.id)
            if not parent_msg.embeds:
                return await ctx.send("❌ No encontré el embed de la actividad.", delete_after=5)

            embed = parent_msg.embeds[0]
            menciones = [
                line[line.find("<@"):line.find(">") + 1]
                for line in embed.description.split("\n")
                if "<@" in line
            ]

            # Marcar actividad como finalizada en el embed
            embed.title = f"🏁 {embed.title} - FINALIZADA"
            embed.color = discord.Color.red()
            await parent_msg.edit(embed=embed)

            # Guardar asistencias en Supabase
            pings_cog = self.bot.cogs.get('PingsAlbion')
            registro_id = pings_cog.active_registros.pop(ctx.channel.id, None) if pings_cog else None

            if registro_id and menciones:
                asistencias_data = []
                for mencion in menciones:
                    user_id = mencion[2:-1].replace('!', '')
                    member = ctx.guild.get_member(int(user_id))
                    nombre = member.display_name if member else user_id
                    asistencias_data.append({
                        'registro_actividad_id': registro_id,
                        'usuario_id': user_id,
                        'usuario_nombre': nombre
                    })
                await asyncio.to_thread(
                    lambda: get_db().table('asistencias').insert(asistencias_data).execute()
                )

            msg_final = f"✅ Actividad finalizada por {ctx.author.mention}.\n"
            if menciones:
                msg_final += f"Participantes: {' '.join(menciones)}"

            await ctx.send(msg_final)
            await ctx.channel.edit(locked=True, archived=True)

        except Exception as e:
            await ctx.send(f"❌ No pude cerrar la actividad correctamente: {e}", delete_after=5)

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
    @app_commands.describe(
        member="Miembro a silenciar",
        minutos="Duración del silencio en minutos",
        razon="Motivo del silencio"
    )
    @commands.has_any_role("Oficial", "Guild Master")
    async def timeout_user(self, ctx, member: discord.Member, minutos: int, *, razon: str = "No especificada"):
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("⚠️ El bot no tiene permiso de 'Moderar miembros'.", delete_after=10)

        roles_protegidos = ["Oficial", "Guild Master"]
        if any(r.name in roles_protegidos for r in member.roles):
            return await ctx.send(f"❌ No se puede silenciar a **{member.display_name}** porque tiene un rol protegido (Oficial o Guild Master).", delete_after=10)

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
                await interaction.response.edit_message(
                    content=f"✅ **{self.target.display_name}** expulsado.", view=None
                )
            elif self.accion == "silenciar":
                duracion = datetime.timedelta(minutes=self.tiempo)
                await self.target.timeout(duracion, reason=self.razon)
                await interaction.response.edit_message(
                    content=f"✅ **{self.target.display_name}** silenciado por {self.tiempo} minutos.", view=None
                )
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error técnico: {e}", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Acción cancelada.", view=None)


async def setup(bot):
    await bot.add_cog(Moderacion(bot))

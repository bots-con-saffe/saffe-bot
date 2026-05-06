import discord
from discord.ext import commands
import datetime

class Moderacion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- TU COMANDO CLEAR ---
    @commands.command(name="clear", aliases=["borrar", "limpiar"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, cantidad: int = 5):
        borrados = await ctx.channel.purge(limit=cantidad + 1)
        await ctx.send(f"✅ Listo. Se han borrado **{len(borrados) - 1}** mensajes.", delete_after=3)

    # --- COMANDO CALLOUT PARA CERRAR ACTIVIDADES ---
    @commands.command(name="callout")
    @commands.has_any_role("Oficial", "Guild Master")
    async def callout(self, ctx):
        try: await ctx.message.delete()
        except: pass

        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa esto dentro del hilo de la actividad.", delete_after=5)

        try:
            parent_msg = await ctx.channel.parent.fetch_message(ctx.channel.id)
            if parent_msg.embeds:
                embed = parent_msg.embeds[0]
                menciones = [line[line.find("<@"):line.find(">")+1] for line in embed.description.split("\n") if "<@" in line]
                
                embed.title = f"🏁 {embed.title} - FINALIZADA"
                embed.color = discord.Color.red()
                await parent_msg.edit(embed=embed)

                msg_final = f"✅ Actividad finalizada por {ctx.author.mention}.\n"
                if menciones: msg_final += f"Participantes: {' '.join(menciones)}"
                
                await ctx.send(msg_final)
                await ctx.channel.edit(locked=True, archived=True)
        except:
            await ctx.send("❌ No pude cerrar la actividad correctamente.", delete_after=5)

    # --- COMANDOS DE MODERACIÓN (!kick y !timeout) ---
    @commands.command(name="kick")
    @commands.has_any_role("Oficial", "Guild Master")
    async def kick_user(self, ctx, member: discord.Member, *, razon="No especificada"):
        view = ConfirmacionMod(member, "expulsar", razon)
        await ctx.send(f"⚠️ {ctx.author.mention}, ¿confirmas **expulsar** a {member.mention}?\nMotivo: {razon}", view=view)

    @commands.command(name="timeout")
    @commands.has_any_role("Oficial", "Guild Master")
    async def timeout_user(self, ctx, member: discord.Member, minutos: int, *, razon: str = "No especificada"):
        """Uso: !timeout @usuario 5 razon"""
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("⚠️ Error: El bot no tiene permiso de 'Moderar miembros'.", delete_after=10)

        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ No puedo silenciar a este usuario (su rango es igual o mayor al mío).", delete_after=10)

        view = ConfirmacionMod(member, "silenciar", razon, minutos)
        await ctx.send(f"⚖️ **SOLICITUD DE TIMEOUT**\n**Usuario:** {member.mention}\n**Duración:** {minutos} minutos\n**Razón:** {razon}\n\n¿Confirmas esta acción, {ctx.author.mention}?", view=view)

    # --- MANEJO DE ERRORES ---
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

# --- CLASE DE BOTONES ---
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
                await interaction.response.edit_message(content=f"✅ **{self.target.display_name}** ha sido silenciado por {self.tiempo} minutos.", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error técnico: {e}", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Acción cancelada.", view=None)

async def setup(bot):
    await bot.add_cog(Moderacion(bot))
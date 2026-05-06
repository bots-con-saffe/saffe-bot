import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from db import get_db


def formatear(cantidad: int) -> str:
    """Formatea un número con separadores de miles. Ej: 1500000 → 1.500.000"""
    return f"{cantidad:,}".replace(",", ".")


def extraer_participantes(embed: discord.Embed) -> list[str]:
    """Extrae los IDs de usuario de las menciones en el embed de una actividad."""
    ids = []
    for line in embed.description.split("\n"):
        if "<@" in line:
            start = line.find("<@")
            end = line.find(">", start) + 1
            user_id = line[start:end][2:-1].replace("!", "")
            if user_id not in ids:
                ids.append(user_id)
    return ids


class Silver(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- SPLIT ---

    @commands.hybrid_command(name="split", description="Calcula y reparte el silver de una actividad entre los participantes")
    @app_commands.describe(
        bolsas="Silver en bolsas (sin puntos ni comas)",
        loot="Estimado del loot en silver (sin puntos ni comas)"
    )
    @commands.has_any_role("Oficial", "Guild Master")
    async def split(self, ctx, bolsas: int, loot: int = 0):
        await ctx.defer()

        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("❌ Usa este comando dentro del hilo de una actividad.", delete_after=5)

        # Leer participantes del embed del hilo
        try:
            parent_msg = await ctx.channel.parent.fetch_message(ctx.channel.id)
        except Exception:
            return await ctx.send("❌ No pude encontrar el embed de la actividad.", delete_after=5)

        if not parent_msg.embeds:
            return await ctx.send("❌ No hay un embed de actividad en este hilo.", delete_after=5)

        participante_ids = extraer_participantes(parent_msg.embeds[0])

        if not participante_ids:
            return await ctx.send("❌ No hay participantes anotados en la actividad.", delete_after=5)

        # Cálculo
        total_bruto = bolsas + loot
        descuento = int(total_bruto * 0.15)
        total_neto = total_bruto - descuento
        por_persona = total_neto // len(participante_ids)

        # Obtener miembros del servidor para mostrar nombres
        menciones = [f"<@{uid}>" for uid in participante_ids]

        embed = discord.Embed(title="💰 Resumen del Split", color=discord.Color.gold())
        embed.add_field(name="Silver en bolsas", value=formatear(bolsas), inline=True)
        embed.add_field(name="Estimado loot", value=formatear(loot), inline=True)
        embed.add_field(name="Total bruto", value=formatear(total_bruto), inline=False)
        embed.add_field(name="Descuento guild (15%)", value=f"-{formatear(descuento)}", inline=True)
        embed.add_field(name="Total neto", value=formatear(total_neto), inline=True)
        embed.add_field(
            name=f"Por persona ({len(participante_ids)} participantes)",
            value=f"**{formatear(por_persona)}** silver",
            inline=False
        )
        embed.add_field(name="Participantes", value=" ".join(menciones), inline=False)
        embed.set_footer(text="¿Confirmas el reparto?")

        view = ConfirmacionSplit(
            participante_ids=participante_ids,
            por_persona=por_persona,
            actividad=parent_msg.embeds[0].title,
            guild=ctx.guild
        )
        await ctx.send(embed=embed, view=view)

    # --- BALANCE ---

    @commands.hybrid_command(name="balance", description="Consulta el balance de silver acumulado")
    @app_commands.describe(usuario="Miembro a consultar (solo Oficial/GM)")
    async def balance(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        # Si se especifica otro usuario, requiere rol
        if usuario and usuario != ctx.author:
            roles_permitidos = ["Oficial", "Guild Master"]
            if not any(r.name in roles_permitidos for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden consultar el balance de otros.", delete_after=5)
            target = usuario
        else:
            target = ctx.author

        result = await asyncio.to_thread(
            lambda: get_db().table('balances')
                .select('balance')
                .eq('usuario_id', str(target.id))
                .execute()
        )

        balance = result.data[0]['balance'] if result.data else 0

        embed = discord.Embed(
            title=f"💰 Balance de {target.display_name}",
            description=f"**{formatear(balance)}** silver",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    # --- HISTORIAL ---

    @commands.hybrid_command(name="historial", description="Muestra las últimas transacciones de silver")
    @app_commands.describe(usuario="Miembro a consultar (solo Oficial/GM)")
    async def historial(self, ctx, usuario: discord.Member = None):
        await ctx.defer(ephemeral=True)

        if usuario and usuario != ctx.author:
            roles_permitidos = ["Oficial", "Guild Master"]
            if not any(r.name in roles_permitidos for r in ctx.author.roles):
                return await ctx.send("❌ Solo Oficiales y Guild Masters pueden ver el historial de otros.", delete_after=5)
            target = usuario
        else:
            target = ctx.author

        result = await asyncio.to_thread(
            lambda: get_db().table('transacciones')
                .select('tipo, cantidad, motivo, fecha')
                .eq('usuario_id', str(target.id))
                .order('fecha', desc=True)
                .limit(10)
                .execute()
        )

        if not result.data:
            return await ctx.send(f"No hay transacciones registradas para **{target.display_name}**.", delete_after=7)

        embed = discord.Embed(title=f"📋 Historial de {target.display_name}", color=discord.Color.blurple())
        for tx in result.data:
            signo = "+" if tx['cantidad'] > 0 else ""
            fecha = tx['fecha'][:10]
            embed.add_field(
                name=f"{signo}{formatear(tx['cantidad'])} silver — {fecha}",
                value=f"`{tx['tipo']}` · {tx['motivo'] or 'Sin motivo'}",
                inline=False
            )
        await ctx.send(embed=embed)

    # --- ADD / REMOVE BALANCE ---

    @commands.hybrid_command(name="addbalance", description="Suma silver al balance de un miembro manualmente")
    @app_commands.describe(
        usuario="Miembro al que sumar silver",
        cantidad="Cantidad de silver a sumar",
        motivo="Motivo del ajuste"
    )
    @commands.has_any_role("Oficial", "Guild Master")
    async def addbalance(self, ctx, usuario: discord.Member, cantidad: int, *, motivo: str = "Ajuste manual"):
        await ctx.defer(ephemeral=True)
        await _actualizar_balance(usuario, cantidad, "ajuste_manual", motivo)
        await ctx.send(f"✅ Se sumaron **{formatear(cantidad)}** silver a {usuario.mention}.", delete_after=5)

    @commands.hybrid_command(name="removebalance", description="Resta silver del balance de un miembro manualmente")
    @app_commands.describe(
        usuario="Miembro al que restar silver",
        cantidad="Cantidad de silver a restar",
        motivo="Motivo del ajuste"
    )
    @commands.has_any_role("Oficial", "Guild Master")
    async def removebalance(self, ctx, usuario: discord.Member, cantidad: int, *, motivo: str = "Ajuste manual"):
        await ctx.defer(ephemeral=True)
        await _actualizar_balance(usuario, -cantidad, "ajuste_manual", motivo)
        await ctx.send(f"✅ Se restaron **{formatear(cantidad)}** silver a {usuario.mention}.", delete_after=5)


# --- FUNCIÓN AUXILIAR ---

async def _actualizar_balance(member: discord.Member, cantidad: int, tipo: str, motivo: str):
    """Actualiza el balance de un usuario y registra la transacción."""
    user_id = str(member.id)
    nombre = member.display_name

    # Obtener balance actual
    result = await asyncio.to_thread(
        lambda: get_db().table('balances')
            .select('balance')
            .eq('usuario_id', user_id)
            .execute()
    )

    balance_actual = result.data[0]['balance'] if result.data else 0
    nuevo_balance = balance_actual + cantidad

    # Upsert balance
    await asyncio.to_thread(
        lambda: get_db().table('balances')
            .upsert({'usuario_id': user_id, 'usuario_nombre': nombre, 'balance': nuevo_balance}, on_conflict='usuario_id')
            .execute()
    )

    # Registrar transacción
    await asyncio.to_thread(
        lambda: get_db().table('transacciones')
            .insert({'usuario_id': user_id, 'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo})
            .execute()
    )


# --- BOTONES DE CONFIRMACIÓN DEL SPLIT ---

class ConfirmacionSplit(discord.ui.View):
    def __init__(self, participante_ids: list[str], por_persona: int, actividad: str, guild: discord.Guild):
        super().__init__(timeout=60)
        self.participante_ids = participante_ids
        self.por_persona = por_persona
        self.actividad = actividad
        self.guild = guild

    @discord.ui.button(label="Confirmar reparto", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_permitidos = ["Oficial", "Guild Master"]
        if not any(r.name in roles_permitidos for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Solo Oficiales y Guild Masters pueden confirmar el reparto.", ephemeral=True)

        await interaction.response.edit_message(content="⏳ Procesando...", embed=None, view=None)

        for user_id in self.participante_ids:
            member = self.guild.get_member(int(user_id))
            if member:
                await _actualizar_balance(member, self.por_persona, "split", f"Split: {self.actividad}")

        await interaction.edit_original_response(
            content=f"✅ Split confirmado. Se repartieron **{formatear(self.por_persona)}** silver a {len(self.participante_ids)} participantes."
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Split cancelado.", embed=None, view=None)


async def setup(bot):
    await bot.add_cog(Silver(bot))

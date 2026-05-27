import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from db import get_db, get_balance_lock
from cogs.silver import _actualizar_balance

BANCO_ID   = "BANCO_GREMIO"
MAX_APUESTA = 500_000

# ── Dados ────────────────────────────────────────────────────────────────────
DADO_EMO = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

# ── Blackjack ────────────────────────────────────────────────────────────────
PALOS   = ["♠", "♥", "♦", "♣"]
VALORES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def nueva_baraja() -> list[str]:
    return [f"{v}{p}" for p in PALOS for v in VALORES]

def valor_carta(carta: str) -> int:
    v = carta[:-1]
    if v in ("J", "Q", "K"): return 10
    if v == "A":              return 11
    return int(v)

def calcular_mano(mano: list[str]) -> int:
    total = sum(valor_carta(c) for c in mano)
    ases  = sum(1 for c in mano if c[:-1] == "A")
    while total > 21 and ases:
        total -= 10
        ases  -= 1
    return total

def render_mano(mano: list[str], ocultar_segunda: bool = False) -> str:
    if ocultar_segunda:
        cartas = [f"`{mano[0]}`", "`??`"]
    else:
        cartas = [f"`{c}`" for c in mano]
    return "  ".join(cartas)


class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot          = bot
        self.jugando      = set()   # user IDs con juego activo
        self.ruleta_activa = False

    # ── utilidades ────────────────────────────────────────────────────────────

    def fmt(self, n: int) -> str:
        return f"{n:,}".replace(",", ".")

    def cvt(self, s: str) -> int:
        t = str(s).lower().strip()
        try:
            if t.endswith("k"): return int(float(t[:-1]) * 1_000)
            if t.endswith("m"): return int(float(t[:-1]) * 1_000_000)
            return int(float(t))
        except Exception:
            return 0

    async def get_banco(self) -> int:
        r = await asyncio.to_thread(
            lambda: get_db().table("balances").select("balance")
                .eq("usuario_id", BANCO_ID).execute()
        )
        return r.data[0]["balance"] if r.data else 0

    async def mover_banco(self, cantidad: int, tipo: str, motivo: str):
        async with get_balance_lock(BANCO_ID):
            banco = await self.get_banco()
            nuevo = banco + cantidad
            await asyncio.to_thread(
                lambda: get_db().table("balances").upsert(
                    {"usuario_id": BANCO_ID, "usuario_nombre": "🏦 Banco del Gremio", "balance": nuevo},
                    on_conflict="usuario_id"
                ).execute()
            )
            await asyncio.to_thread(
                lambda: get_db().table("transacciones").insert(
                    {"usuario_id": BANCO_ID, "tipo": tipo, "cantidad": cantidad, "motivo": motivo}
                ).execute()
            )

    async def validar_apuesta(self, ctx, valor: int) -> bool:
        if valor <= 0:
            await ctx.send("❌ La apuesta debe ser mayor a 0.", delete_after=5)
            return False
        if valor > MAX_APUESTA:
            await ctx.send(f"❌ La apuesta máxima contra la casa es **{self.fmt(MAX_APUESTA)}** silver.", delete_after=5)
            return False
        r = await asyncio.to_thread(
            lambda: get_db().table("balances").select("balance")
                .eq("usuario_id", str(ctx.author.id)).execute()
        )
        saldo = r.data[0]["balance"] if r.data else 0
        if saldo < valor:
            await ctx.send(f"❌ No tienes suficiente silver. Tienes **{self.fmt(saldo)}**.", delete_after=5)
            return False
        banco = await self.get_banco()
        if banco < valor * 2:
            await ctx.send(
                f"❌ El banco del gremio no tiene fondos suficientes para cubrir esta apuesta.\n"
                f"Reservas actuales: **{self.fmt(banco)}** silver. Pide a un GM que deposite más.",
                delete_after=8
            )
            return False
        return True

    # ── BANCO ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="banco_balance", description="Muestra el balance del banco del gremio")
    @commands.has_any_role("Oficial", "Guild Master")
    async def banco_balance(self, ctx):
        banco = await self.get_banco()
        embed = discord.Embed(
            title="🏦 Banco del Gremio",
            description=f"**Reservas actuales:** {self.fmt(banco)} silver",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Usa /banco_depositar para añadir fondos")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="banco_depositar", description="Añade silver al banco del gremio")
    @app_commands.describe(cantidad="Cantidad a depositar (Ej: 5m, 500k)")
    @commands.has_any_role("Oficial", "Guild Master")
    async def banco_depositar(self, ctx, cantidad: str):
        valor = self.cvt(cantidad)
        if valor <= 0:
            return await ctx.send("❌ Cantidad inválida.", delete_after=5)
        await self.mover_banco(valor, "deposito", f"Depósito por {ctx.author.display_name}")
        banco = await self.get_banco()
        await ctx.send(embed=discord.Embed(
            title="🏦 Depósito realizado",
            description=f"Se añadieron **{self.fmt(valor)}** silver.\n**Nuevo balance:** {self.fmt(banco)} silver",
            color=discord.Color.green()
        ))

    # ── RULETA RUSA ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ruleta", description="🔫 Ruleta Rusa — jugadores entre sí")
    @app_commands.describe(apuesta="Precio del asiento (Ej: 500k, 1m)")
    async def ruleta(self, ctx, apuesta: str):
        if self.ruleta_activa:
            return await ctx.send("❌ Ya hay una mesa activa.", delete_after=5)

        valor = self.cvt(apuesta)
        if valor <= 0:
            return await ctx.send("❌ Apuesta inválida.", delete_after=5)

        r = await asyncio.to_thread(
            lambda: get_db().table("balances").select("balance")
                .eq("usuario_id", str(ctx.author.id)).execute()
        )
        saldo = r.data[0]["balance"] if r.data else 0
        if saldo < valor:
            return await ctx.send(f"❌ No tienes suficiente silver. Tienes **{self.fmt(saldo)}**.", delete_after=5)

        self.ruleta_activa = True
        self.jugando.add(str(ctx.author.id))
        await _actualizar_balance(ctx.author, -valor, "entrada_ruleta", "Entrada Ruleta Rusa")

        view = RuletaView(self, valor, ctx)
        msg  = await ctx.send(embed=self._embed_ruleta_lobby(view.jugadores, valor), view=view)

        # El juego corre en background; el comando responde de inmediato
        asyncio.create_task(self._jugar_ruleta(ctx, view, msg, valor))

    async def _jugar_ruleta(self, ctx, view: "RuletaView", msg: discord.Message, valor: int):
        mensajes_tmp = []
        try:
            await view.wait()

            if len(view.jugadores) < 2:
                await _actualizar_balance(ctx.author, valor, "reembolso_ruleta", "Reembolso Ruleta (Cancelada)")
                await msg.edit(embed=discord.Embed(
                    title="🚫 Ruleta Cancelada",
                    description="Nadie se unió a tiempo. Se devolvió la apuesta.",
                    color=discord.Color.dark_grey()
                ), view=None)
                return

            await msg.delete()

            jugadores_vivos = view.jugadores.copy()
            eliminados      = []
            random.shuffle(jugadores_vivos)
            idx = 0

            while len(jugadores_vivos) > 1:
                bala         = random.randint(1, 6)
                tambor       = 1
                ronda_activa = True

                while ronda_activa and len(jugadores_vivos) > 1:
                    if idx >= len(jugadores_vivos):
                        idx = 0
                    jugador = jugadores_vivos[idx]

                    m = await ctx.send(f"🔫 **{jugador.display_name}** aprieta el gatillo...")
                    mensajes_tmp.append(m)
                    await asyncio.sleep(2)

                    if tambor == bala:
                        await m.edit(content=f"💥 **{jugador.display_name}** ha caído.")
                        eliminados.append(jugador)
                        jugadores_vivos.remove(jugador)
                        ronda_activa = False
                        await asyncio.sleep(1)
                    else:
                        await m.edit(content=f"😮‍💨 **{jugador.display_name}** — *click*. Sigue vivo.")
                        tambor += 1
                        idx    += 1
                        await asyncio.sleep(1)

            # Borrar todos los mensajes intermedios
            for m in mensajes_tmp:
                try:
                    await m.delete()
                except Exception:
                    pass

            ganador = jugadores_vivos[0]
            bote    = valor * len(view.jugadores)
            await _actualizar_balance(ganador, bote, "premio_ruleta", "Premio Mayor Ruleta Rusa")

            resumen_eliminados = "\n".join(f"💀 {j.display_name}" for j in eliminados)
            embed = discord.Embed(title="🔫 Ruleta Rusa — Resultado", color=discord.Color.dark_red())
            embed.add_field(name="Eliminados", value=resumen_eliminados or "—", inline=False)
            embed.add_field(
                name="🏆 Superviviente",
                value=f"{ganador.mention} se lleva **{self.fmt(bote)} silver**",
                inline=False
            )
            await ctx.send(embed=embed)

        except Exception as e:
            try:
                await ctx.send(f"❌ Error interno en la ruleta: {e}", delete_after=10)
            except Exception:
                pass
        finally:
            self.ruleta_activa = False
            for j in view.jugadores:
                self.jugando.discard(str(j.id))

    def _embed_ruleta_lobby(self, jugadores: list, valor: int) -> discord.Embed:
        lista = "\n".join(f"🔫 {j.display_name}" for j in jugadores)
        bote  = valor * len(jugadores)
        return discord.Embed(
            title="🔫 RULETA RUSA",
            description=(
                "```\n"
                "╔══════════════════════════╗\n"
                "║  ○  ○  ○  💀  ○  ○      ║\n"
                "║  ↑  tambor oculto        ║\n"
                "╚══════════════════════════╝\n"
                "```\n"
                f"**Asiento:** {self.fmt(valor)} silver  •  máx. 6 jugadores"
            ),
            color=discord.Color.dark_red()
        ).add_field(
            name=f"Jugadores ({len(jugadores)})",
            value=lista,
            inline=False
        ).add_field(
            name="🪙 Bote acumulado",
            value=f"**{self.fmt(bote)}** silver",
            inline=False
        )

    # ── DADOS (vs casa) ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="dados", description="🎲 Tira un dado contra la casa — el mayor gana")
    @app_commands.describe(apuesta="Plata a apostar (máx 500k — Ej: 100k)")
    async def dados(self, ctx, apuesta: str):
        valor = self.cvt(apuesta)
        if not await self.validar_apuesta(ctx, valor):
            return
        if str(ctx.author.id) in self.jugando:
            return await ctx.send("❌ Ya tienes un juego activo.", delete_after=5)

        self.jugando.add(str(ctx.author.id))
        try:
            await _actualizar_balance(ctx.author, -valor, "entrada_casino", "Entrada Dados")
            await self.mover_banco(valor, "ingreso_casino", "Entrada Dados")

            # Animación de dados girando
            msg = await ctx.send(embed=discord.Embed(
                title="🎲 DADOS vs CASA",
                description="```\n  🎲  Los dados ruedan...\n```",
                color=discord.Color.blurple()
            ))
            for _ in range(3):
                await asyncio.sleep(0.9)
                r1, r2 = random.randint(1, 6), random.randint(1, 6)
                await msg.edit(embed=discord.Embed(
                    title="🎲 DADOS vs CASA",
                    description=f"```\n  TÚ  {DADO_EMO[r1]}   vs   {DADO_EMO[r2]}  CASA\n```",
                    color=discord.Color.blurple()
                ))

            await asyncio.sleep(0.9)
            tu_dado   = random.randint(1, 6)
            casa_dado = random.randint(1, 6)

            if tu_dado > casa_dado:
                titulo = "🎲 ¡GANASTE!"
                color  = discord.Color.green()
                delta  = valor
                await _actualizar_balance(ctx.author, valor * 2, "premio_casino", f"Dados — ganancia +{self.fmt(valor)}")
                await self.mover_banco(-valor * 2, "pago_casino", f"Dados — pago a {ctx.author.display_name}")
                resultado = f"✅ **+{self.fmt(delta)} silver**"
            elif tu_dado < casa_dado:
                titulo    = "🎲 PERDISTE"
                color     = discord.Color.red()
                resultado = f"❌ **-{self.fmt(valor)} silver**"
            else:
                titulo = "🎲 EMPATE — Bote devuelto"
                color  = discord.Color.greyple()
                await _actualizar_balance(ctx.author, valor, "empate_casino", "Dados — Empate")
                await self.mover_banco(-valor, "empate_casino", "Dados — Empate")
                resultado = "↩️ Se devuelve tu apuesta"

            desc = (
                "```\n"
                f"  TÚ              CASA\n"
                f"   {DADO_EMO[tu_dado]}    vs    {DADO_EMO[casa_dado]}\n"
                f"   {tu_dado}    vs    {casa_dado}\n"
                "```\n"
                f"{resultado}"
            )
            await msg.edit(embed=discord.Embed(title=titulo, description=desc, color=color))

        finally:
            self.jugando.discard(str(ctx.author.id))

    # ── BLACKJACK (vs casa) ───────────────────────────────────────────────────

    @commands.hybrid_command(name="blackjack", description="🃏 Blackjack contra la casa — llega a 21")
    @app_commands.describe(apuesta="Plata a apostar (máx 500k — Ej: 200k)")
    async def blackjack(self, ctx, apuesta: str):
        valor = self.cvt(apuesta)
        if not await self.validar_apuesta(ctx, valor):
            return
        if str(ctx.author.id) in self.jugando:
            return await ctx.send("❌ Ya tienes un juego activo.", delete_after=5)

        self.jugando.add(str(ctx.author.id))
        try:
            await _actualizar_balance(ctx.author, -valor, "entrada_casino", "Entrada Blackjack")
            await self.mover_banco(valor, "ingreso_casino", "Entrada Blackjack")

            baraja     = nueva_baraja()
            random.shuffle(baraja)
            mano_j     = [baraja.pop(), baraja.pop()]
            mano_c     = [baraja.pop(), baraja.pop()]
            total_j    = calcular_mano(mano_j)

            # Blackjack natural inmediato
            if total_j == 21:
                total_c = calcular_mano(mano_c)
                if total_c == 21:
                    await _actualizar_balance(ctx.author, valor, "empate_casino", "BJ Natural — Empate")
                    await self.mover_banco(-valor, "empate_casino", "BJ Natural — Empate")
                    titulo, color, extra = "🃏 EMPATE — Ambos tienen Blackjack", discord.Color.greyple(), "Se devuelve tu apuesta."
                else:
                    premio = int(valor * 1.5)
                    await _actualizar_balance(ctx.author, valor + premio, "premio_casino", f"BJ Natural +{self.fmt(premio)}")
                    await self.mover_banco(-(valor + premio), "pago_casino", f"BJ Natural a {ctx.author.display_name}")
                    titulo, color, extra = "🃏 ¡BLACKJACK NATURAL! 🎉", discord.Color.gold(), f"Ganas **{self.fmt(premio)}** silver extra."
                embed = self._embed_bj(mano_j, mano_c, total_j, total_c, False)
                embed.title       = titulo
                embed.color       = color
                embed.description = extra
                return await ctx.send(embed=embed)

            view      = BlackjackView(self, mano_j, mano_c, baraja, valor, ctx)
            embed     = self._embed_bj(mano_j, mano_c, total_j, None, True)
            msg       = await ctx.send(embed=embed, view=view)
            view.msg  = msg
            await view.wait()

        finally:
            self.jugando.discard(str(ctx.author.id))

    def _embed_bj(self, mano_j, mano_c, total_j, total_c, ocultar) -> discord.Embed:
        cartas_j = render_mano(mano_j)
        cartas_c = render_mano(mano_c, ocultar)
        if ocultar:
            info_c = f"Carta visible: **{mano_c[0]}**"
        else:
            tc     = total_c if total_c is not None else calcular_mano(mano_c)
            info_c = f"Total: **{tc}**{'  💥 ¡PASADO!' if tc > 21 else ''}"

        return discord.Embed(
            title="🃏 BLACKJACK",
            color=discord.Color.blurple()
        ).add_field(
            name=f"Tu mano — Total: {total_j}{'  💥' if total_j > 21 else ''}",
            value=cartas_j,
            inline=False
        ).add_field(
            name="Casa",
            value=f"{cartas_c}\n{info_c}",
            inline=False
        )


# ── Views ─────────────────────────────────────────────────────────────────────

class RuletaView(discord.ui.View):
    def __init__(self, cog, valor, ctx):
        super().__init__(timeout=300)
        self.cog    = cog
        self.valor  = valor
        self.ctx    = ctx
        self.jugadores = [ctx.author]

    @discord.ui.button(label="✅ Unirse", style=discord.ButtonStyle.green)
    async def btn_unirse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.jugadores) >= 6:
            return await interaction.response.send_message("❌ Mesa llena (máx 6).", ephemeral=True)
        if not self.cog.ruleta_activa:
            return await interaction.response.send_message("❌ La mesa ya cerró.", ephemeral=True)
        if interaction.user in self.jugadores:
            return await interaction.response.send_message("❌ Ya estás sentado.", ephemeral=True)

        r = await asyncio.to_thread(
            lambda: get_db().table("balances").select("balance")
                .eq("usuario_id", str(interaction.user.id)).execute()
        )
        saldo = r.data[0]["balance"] if r.data else 0
        if saldo < self.valor:
            return await interaction.response.send_message(
                f"❌ Necesitas **{self.cog.fmt(self.valor)}** silver.", ephemeral=True
            )

        if str(interaction.user.id) in self.cog.jugando:
            return await interaction.response.send_message("❌ Ya tienes otro juego activo.", ephemeral=True)

        await _actualizar_balance(interaction.user, -self.valor, "entrada_ruleta", "Entrada Ruleta Rusa")
        self.cog.jugando.add(str(interaction.user.id))
        self.jugadores.append(interaction.user)
        await interaction.response.send_message("✅ Entraste a la mesa.", ephemeral=True)
        await interaction.message.edit(
            embed=self.cog._embed_ruleta_lobby(self.jugadores, self.valor)
        )

    @discord.ui.button(label="🚀 Iniciar ya", style=discord.ButtonStyle.blurple)
    async def btn_iniciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ Solo el creador puede forzar el inicio.", ephemeral=True)
        self.stop()
        await interaction.response.defer()


class BlackjackView(discord.ui.View):
    def __init__(self, cog, mano_j, mano_c, baraja, valor, ctx):
        super().__init__(timeout=60)
        self.cog    = cog
        self.mano_j = mano_j
        self.mano_c = mano_c
        self.baraja = baraja
        self.valor  = valor
        self.ctx    = ctx
        self.msg    = None

    async def on_timeout(self):
        if self.msg:
            await self.msg.edit(embed=discord.Embed(
                title="🃏 Tiempo agotado — Perdiste",
                description="No respondiste a tiempo. La apuesta se pierde.",
                color=discord.Color.red()
            ), view=None)
        self.cog.jugando.discard(str(self.ctx.author.id))

    async def _resolver(self, interaction: discord.Interaction):
        while calcular_mano(self.mano_c) < 17:
            self.mano_c.append(self.baraja.pop())

        total_j = calcular_mano(self.mano_j)
        total_c = calcular_mano(self.mano_c)
        embed   = self.cog._embed_bj(self.mano_j, self.mano_c, total_j, total_c, False)

        if total_j > 21:
            embed.title = "🃏 ¡TE PASASTE! Perdiste."
            embed.color = discord.Color.red()
        elif total_c > 21 or total_j > total_c:
            embed.title       = "🃏 ¡GANASTE!"
            embed.color       = discord.Color.green()
            embed.description = f"Ganancia: **+{self.cog.fmt(self.valor)}** silver"
            await _actualizar_balance(self.ctx.author, self.valor * 2, "premio_casino", f"BJ win +{self.cog.fmt(self.valor)}")
            await self.cog.mover_banco(-self.valor * 2, "pago_casino", f"BJ pago a {self.ctx.author.display_name}")
        elif total_j == total_c:
            embed.title       = "🃏 EMPATE — Se devuelve tu apuesta"
            embed.color       = discord.Color.greyple()
            await _actualizar_balance(self.ctx.author, self.valor, "empate_casino", "BJ Empate")
            await self.cog.mover_banco(-self.valor, "empate_casino", "BJ Empate")
        else:
            embed.title = "🃏 PERDISTE"
            embed.color = discord.Color.red()

        await self.msg.edit(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="🃏 Pedir", style=discord.ButtonStyle.green)
    async def btn_pedir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ No es tu juego.", ephemeral=True)

        self.mano_j.append(self.baraja.pop())
        total = calcular_mano(self.mano_j)

        if total > 21:
            embed = self.cog._embed_bj(self.mano_j, self.mano_c, total, calcular_mano(self.mano_c), False)
            embed.title = "🃏 ¡TE PASASTE! Perdiste."
            embed.color = discord.Color.red()
            await self.msg.edit(embed=embed, view=None)
            self.stop()
        else:
            await self.msg.edit(embed=self.cog._embed_bj(self.mano_j, self.mano_c, total, None, True))

        await interaction.response.defer()

    @discord.ui.button(label="✋ Plantarse", style=discord.ButtonStyle.red)
    async def btn_plantarse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ No es tu juego.", ephemeral=True)
        await interaction.response.defer()
        await self._resolver(interaction)

    @discord.ui.button(label="✌️ Doblar", style=discord.ButtonStyle.blurple)
    async def btn_doblar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ No es tu juego.", ephemeral=True)

        r = await asyncio.to_thread(
            lambda: get_db().table("balances").select("balance")
                .eq("usuario_id", str(self.ctx.author.id)).execute()
        )
        saldo = r.data[0]["balance"] if r.data else 0
        if saldo < self.valor:
            return await interaction.response.send_message(
                f"❌ No tienes suficiente silver para doblar ({self.cog.fmt(self.valor)} requerido).", ephemeral=True
            )
        banco = await self.cog.get_banco()
        if banco < self.valor * 4:
            return await interaction.response.send_message(
                "❌ El banco no tiene fondos para cubrir la apuesta doble.", ephemeral=True
            )

        await _actualizar_balance(self.ctx.author, -self.valor, "entrada_casino", "Doble Blackjack")
        await self.cog.mover_banco(self.valor, "ingreso_casino", "Doble Blackjack")
        self.valor *= 2

        self.mano_j.append(self.baraja.pop())   # solo una carta más al doblar
        await interaction.response.defer()
        await self._resolver(interaction)


async def setup(bot):
    await bot.add_cog(Casino(bot))

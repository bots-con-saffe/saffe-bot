import discord
from discord.ext import commands
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def cargar_modulos():
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')

    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            nombre_modulo = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(nombre_modulo)
                print(f"⚙️ Módulo cargado exitosamente: {nombre_modulo}")
            except Exception as e:
                print(f"❌ Error al cargar el módulo {nombre_modulo}:\n{e}")

bot.setup_hook = cargar_modulos

# --- COMANDOS DE ADMINISTRACIÓN ---

@bot.command()
@commands.has_permissions(administrator=True)
async def reload(ctx, modulo: str = "todos"):
    try:
        await ctx.message.delete()
    except: pass

    if modulo == "todos":
        cargados = 0
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                nombre_modulo = f"cogs.{filename[:-3]}"
                try:
                    await bot.reload_extension(nombre_modulo)
                    cargados += 1
                except Exception as e:
                    await ctx.send(f"❌ Error al recargar `{nombre_modulo}`:\n```py\n{e}\n```")
        await ctx.send(f"🔄 ¡Éxito! Se han recargado **{cargados}** módulos.", delete_after=5)
    else:
        try:
            await bot.reload_extension(f"cogs.{modulo}")
            await ctx.send(f"🔄 Módulo `cogs/{modulo}.py` recargado.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Error al recargar `{modulo}`:\n```py\n{e}\n```")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx, guild_id: int = None):
    """Sincroniza los slash commands. Usa !sync para global o !sync [guild_id] para un servidor específico (instantáneo)."""
    try:
        await ctx.message.delete()
    except: pass

    if guild_id:
        guild = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await ctx.send(f"✅ {len(synced)} comandos sincronizados en el servidor `{guild_id}`.", delete_after=10)
    else:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ {len(synced)} comandos sincronizados globalmente (puede tardar hasta 1 hora en aparecer).", delete_after=10)

@bot.command()
@commands.has_permissions(administrator=True)
async def restart(ctx):
    try:
        await ctx.message.delete()
    except: pass

    mensaje = await ctx.send("🔄 Reiniciando el sistema por completo...")
    await asyncio.sleep(2)
    try:
        await mensaje.delete()
    except: pass

    os.execv(sys.executable, ['python'] + sys.argv)

@bot.command()
@commands.has_permissions(administrator=True)
async def limpiar_comandos(ctx):
    """Limpia los comandos globales duplicados y deja solo los del servidor."""
    mensaje = await ctx.send("🧹 Iniciando limpieza de comandos fantasma...")
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await mensaje.edit(content=f"✅ Limpieza completada. Discord global ha sido purgado y se han registrado **{len(synced)}** comandos limpios exclusivamente para este servidor.")

@bot.event
async def on_ready():
    print(f'✅ Saffe_bot encendido como: {bot.user}')
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"🔄 Comandos sincronizados automáticamente en: {guild.name} ({len(synced)} comandos)")
    except Exception as e:
        print(f"⚠️ No se pudo sincronizar automáticamente: {e}")
    print(f'💡 Todo listo para el gremio.')

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ ERROR: No se encontró el DISCORD_TOKEN en el archivo .env")

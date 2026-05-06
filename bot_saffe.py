import discord
from discord.ext import commands
import os
import sys
import asyncio 
from dotenv import load_dotenv # Nueva librería para seguridad

# 1. Cargamos las variables de entorno desde el archivo .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 2. Configuración de Intents
intents = discord.Intents.default()
intents.voice_states = True 
intents.message_content = True 
intents.members = True

# 3. Creación del Bot
bot = commands.Bot(command_prefix='!', intents=intents)

# 4. Función para cargar módulos (Cogs)
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

# Asignamos la función de carga al ciclo de inicio del bot
bot.setup_hook = cargar_modulos

# 5. Comandos de administración
@bot.command()
@commands.is_owner()
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

@bot.event
async def on_ready():
    print(f'✅ Saffe_bot encendido como: {bot.user}')

@bot.command()
@commands.is_owner()
async def restart(ctx):
    try:
        await ctx.message.delete()
    except: pass

    mensaje = await ctx.send("🔄 Reiniciando el sistema por completo...")
    await asyncio.sleep(2)
    
    try:
        await mensaje.delete()
    except: pass
        
    # Reinicia el script de Python
    os.execv(sys.executable, ['python'] + sys.argv)

# 6. Arranque seguro
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ ERROR: No se encontró el DISCORD_TOKEN en el archivo .env")
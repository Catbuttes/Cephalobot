import json
import logging as log
from operator import truediv
import os
from threading import Event, Thread

import discord
import prometheus_client
from discord.ext import commands

prometheus_client.start_http_server(8080)
MOD_CHECKS = prometheus_client.Counter("cephalobot_mod_checks_total", "Total times a mod permissions check has been made")
ADMIN_CHECKS = prometheus_client.Counter("cephalobot_admin_checks_total", "Total times a admin permissions check has been made")
BULK_DELETE = prometheus_client.Counter("cephalobot_bulk_delete_total", "Total times a bulk delete has been made")
MSG_RECV = prometheus_client.Counter("cephalobot_msg_recv_total", "Total times a message has been recieved")
MSG_DELETE = prometheus_client.Counter("cephalobot_msg_delete_total", "Total times a message deletion has been made")
MSG_EDIT = prometheus_client.Counter("cephalobot_msg_edit_total", "Total times a message edit has been made")
MEMBER_JOIN = prometheus_client.Counter("cephalobot_member_join_total", "Total times a member has joined")
MEMBER_PART = prometheus_client.Counter("cephalobot_member_part_total", "Total times a member has departed")
ROLES_RESTORE = prometheus_client.Counter("cephalobot_roles_restore_total", "Total times roles have been restored")
BAN = prometheus_client.Counter("cephalobot_ban_total", "Total times ban has been invoked")
MASS_BAN = prometheus_client.Counter("cephalobot_mass_ban_total", "Total times mass ban has been invoked")
ERROR = prometheus_client.Counter("cephalobot_error_total", "Total error count")
CMD_ERROR = prometheus_client.Counter("cephalobot_cmd_error_total", "Total command error count")

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="c!", intents=intents)
info = json.loads(open("/data/Info.json").read())


# Cant get this to work will comment for now
# bot.activity(discord.CustomActivity(name="Use s!help to get started"))

def get_guild_config(guild_thing):
    id = str(guild_thing.guild.id)
    if id not in info:
        info[id] = {}
    return info[id]


def save():
    open("/data/Info.json", "w").write(json.dumps(info))


default_webhook = {"username": "Cephalobot",
                   "avatar_url": "https://cdn.discordapp.com/attachments/278555022646706176/699359432756166716/Cephalobot.png"
                   }


def is_mod():
    def predicate(ctx):
        MOD_CHECKS.inc()
        guild = get_guild_config(ctx)
        if "mod roles" in guild:
            mod_roles = guild["mod roles"]
            roles = ctx.author.roles
            for role in roles:
                if role.id in mod_roles:
                    return True
        return False

    return commands.check(predicate)


def is_admin():
    def predicate(ctx):
        ADMIN_CHECKS.inc()
        guild = get_guild_config(ctx)
        if "admin roles" in guild:
            admin_roles = guild["admin roles"]
            roles = ctx.author.roles
            for role in roles:
                if role.id in admin_roles:
                    return True
        return False

    return commands.check(predicate)


async def webhook_send(channel_id, embed):
    channel = bot.get_channel(channel_id)
    hooks = await channel.webhooks()
    hook = discord.utils.get(hooks, name='Cephalobot:' + str(+channel.id))
    if hook is None:
        hook = await channel.create_webhook(name='Cephalobot:' + str(channel.id))
    guild = get_guild_config(channel)
    if "webhook" not in guild:
        guild["webhook"] = dict(default_webhook)
    webhook_info = guild["webhook"]
    await hook.send(embed=embed, **webhook_info)


async def send_long(ctx, text: str):
    while True:
        if len(text) < 2000:
            await ctx.send(text)
            break
        if "\n" in text:
            pos = text[:2000].rfind(" ")
            await ctx.send(text[:pos])
            text = text[pos + 1:]
        else:
            await ctx.send(text[:2000])
            text = text[2000:]

@bot.event
async def on_command_error(ctx, error):
    CMD_ERROR.inc()

@bot.event
async def on_error(ctx, error):
    ERROR.inc()


@bot.event
async def on_ready():
    global appli
    appli = await bot.application_info()
    print("Logged in! bot invite: https://discordapp.com/api/oauth2/authorize?client_id=" +
          str(appli.id) + "&permissions=7247834116&scope=bot")

@bot.event
async def on_message(message):
    MSG_RECV.inc()
    await bot.process_commands(message)

@bot.event
async def on_bulk_message_delete(messages):
    BULK_DELETE.inc()
    # Logging
    for message in messages:
        await on_message_delete(message)

@bot.event
async def on_message_delete(message):
    MSG_DELETE.inc()
    # Logging
    guild = get_guild_config(message.channel)
    if "message log" in guild:
        log.info("Logging Message Deletion")
        embed = discord.Embed(color=discord.Color.red())
        embed.title = "Deleted Message"
        embed.add_field(name="Username", value=message.author)
        embed.add_field(name="UserId", value=message.author.id, inline=False)
        embed.add_field(name="Channel", value="<#%d>" % message.channel.id, inline=False)
        embed.add_field(name="Content", value=message.content or "Empty Message", inline=False)
        await webhook_send(get_guild_config(message.channel)['message log'], embed)


@bot.event
async def on_message_edit(before, after):
    MSG_EDIT.inc()
    # Logging
    guild = get_guild_config(before.channel)
    if "message log" in guild and before.content != "" and before.content != after.content:
        log.info("Logging Message Edit")
        embed = discord.Embed(color=discord.Color.blue())
        embed.title = "Edited Message"
        embed.add_field(name="Username", value=after.author)
        embed.add_field(name="UserId", value=after.author.id, inline=False)
        embed.add_field(name="Channel", value="<#%d>" % before.channel.id, inline=False)
        embed.add_field(name="Before", value=before.content or "Message Empty", inline=False)
        embed.add_field(name="After", value=after.content or "Message Empty", inline=False)
        await webhook_send(guild['message log'], embed)


@bot.event
async def on_member_remove(member):
    MEMBER_PART.inc()
    # Sticky Role
    guild = get_guild_config(member)
    if "sticky role" in guild and member.guild.get_role(get_guild_config(member)['sticky role']) in member.roles:
        if "evaders" not in guild:
            guild['evaders'] = []
        guild['evaders'].append(member.id)

    # Logging
    if "join log" in guild:
        embed = discord.Embed(color=discord.Color.orange())
        embed.title = "User Left"
        embed.add_field(name="Username", value=member)
        embed.add_field(name="UserId", value=member.id, inline=False)
        await webhook_send(guild['join log'], embed)


@bot.event
async def on_member_join(member):
    MEMBER_JOIN.inc()
    # Sticky Roles
    guild = get_guild_config(member)
    if "sticky role" in guild and "evaders" in guild and member.id in guild['evaders']:
        ROLES_RESTORE.inc()
        await member.add_roles(member.guild.get_role(guild['sticky role']))

    # Logging
    if "join log" in guild:
        embed = discord.Embed(color=discord.Color.blue())
        embed.title = "User Joined"
        embed.add_field(name="Username", value=member)
        embed.add_field(name="UserId", value=member.id, inline=False)
        date = member.created_at
        embed.add_field(name="Account created on", value=str(date)[:str(date).find(".")] + " UTC")
        await webhook_send(guild['join log'], embed)


@bot.group(invoke_without_command=True, aliases=["s"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def settings(ctx):
    """Gives you an overview of your current settings"""
    embed = discord.Embed(title="Displaying Settings")
    guild = get_guild_config(ctx)
    v = None
    if "message log" in guild:
        v = "<#%d>" % guild["message log"]
    embed.add_field(name="Message Log", value=v or "None")
    v = None
    if "join log" in guild:
        v = "<#%d>" % guild["join log"]
    embed.add_field(name="Join Log", value=v or "None")
    v = None
    if "mod roles" in guild:
        v = ""
        for role in guild['mod roles']:
            v += "%s\n" % ctx.guild.get_role(role).name
    embed.add_field(name="Mod Roles", value=v or "None")
    v = None
    if "admin roles" in guild:
        v = ""
        for role in guild['admin roles']:
            v += "%s\n" % ctx.guild.get_role(role).name
    embed.add_field(name="Admin Roles", value=v or "None")
    v = None
    if "sticky role" in guild:
        v = ctx.guild.get_role(guild["sticky role"]).name
    embed.add_field(name="Sticky Role", value=v or "None")
    await ctx.send(embed=embed)


@bot.command()
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def reset(ctx, *, arg: str):
    """Let's you reset a configured setting on the bot valid targets are
    mod roles
    basically lets you instantly remove all mod roles from the bot

    admin roles
    basically lets you instantly remove all admin roles from the bot

    message log
    lets you turn off message logging permanently

    join log
    lets you turn off join log permanently

    webhook
    will reset the loggers appearance to its default(same avatar/name as the bot)

    sticky role
    will remove the sticky role

    evaders
    will allow all current evaders to rejoin without having the sticky role back on them
    """
    if arg not in get_guild_config(ctx):
        await ctx.send("%s is not a valid attribute!" % arg)
        return
    if arg == "admin roles" and (not is_admin()(ctx) and not commands.has_permissions(administrator=True)(ctx)):
        await ctx.send("You must be an Admin or have admin perms to clear Admin roles")
        return
    get_guild_config(ctx).pop(arg)
    await ctx.send("%s has been reset successfully!" % arg)
    save()


@bot.command(aliases=["ml"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def message_log(ctx, channel: discord.TextChannel):
    """Set the message log channel"""
    get_guild_config(ctx)["message log"] = channel.id
    await ctx.send("Successfully set the message log channel to %s" % channel.name)
    save()


@bot.command(aliases=["jl"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def join_log(ctx, channel: discord.TextChannel):
    """Set the join log channel"""
    get_guild_config(ctx)["join log"] = channel.id
    await ctx.send("Successfully set the join log channel to %s" % channel.name)
    save()


@bot.group(invoke_without_command=True, aliases=["mr"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def mod_roles(ctx):
    """Display Mod roles"""
    guild = get_guild_config(ctx)
    if "mod roles" in guild:
        v = ""
        for role in guild['mod roles']:
            v += "\n%s" % ctx.guild.get_role(role).name
        if len(v) == 0:
            v = "\nNone"
    else:
        v = "\nNone"
    await ctx.send("Current modroles:%s" % v)


@mod_roles.command(invoke_without_command=True)
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def add(ctx, role: discord.Role):
    """Add a mod role"""
    guild = get_guild_config(ctx)
    if "mod roles" not in guild:
        guild["mod roles"] = []
    guild["mod roles"].append(role.id)
    await ctx.send("Successfully added %s to the mod roles!" % role.name)
    save()


@mod_roles.command(invoke_without_command=True, aliases=["rem"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def remove(ctx, role: discord.Role):
    """Remove a mod role"""
    get_guild_config(ctx)["mod roles"].remove(role.id)
    await ctx.send("Successfully removed %s from the mod roles!" % role.name)
    save()


@bot.group(invoke_without_command=True, aliases=["ar"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def admin_roles(ctx):
    """Display Admin roles"""
    guild = get_guild_config(ctx)
    if "admin roles" in guild:
        v = ""
        for role in guild['admin roles']:
            v += "\n%s" % ctx.guild.get_role(role).name
        if len(v) == 0:
            v = "\nNone"
    else:
        v = "\nNone"
    await ctx.send("Current adminroles:%s" % v)


@admin_roles.command(invoke_without_command=True)
@commands.check_any(commands.has_permissions(administrator=True), is_admin())
async def add(ctx, role: discord.Role):
    """Add an admin role"""
    guild = get_guild_config(ctx)
    if "admin roles" not in guild:
        guild["admin roles"] = []
    guild["admin roles"].append(role.id)
    await ctx.send("Successfully added %s to the admin roles!" % role.name)
    save()


@admin_roles.command(invoke_without_command=True, aliases=["rem"])
@commands.check_any(commands.has_permissions(administrator=True), is_admin())
async def remove(ctx, role: discord.Role):
    """Remove a admin role"""
    get_guild_config(ctx)["admin roles"].remove(role.id)
    await ctx.send("Successfully removed %s from the admin roles!" % role.name)
    save()


@bot.group(invoke_without_command=True, aliases=["wh"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def webhook(ctx):
    """Shows example webhook"""
    embed = discord.Embed(title="Webhook Example!")
    embed.add_field(name="Sample Text", value="This is what i look like on here!")
    await webhook_send(ctx.channel.id, embed)


@webhook.command()
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def name(ctx, *, arg: str):
    """Set webhook name"""
    guild = get_guild_config(ctx)
    if "webhook" not in guild:
        guild["webhook"] = dict(default_webhook)
    guild["webhook"]["username"] = arg
    await ctx.send("Updated the webhooks name to %s" % arg)
    save()


@webhook.command()
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def avatar(ctx, *, arg: str):
    """Set Webhook avatar"""
    guild = get_guild_config(ctx)
    if "webhook" not in guild:
        guild["webhook"] = dict(default_webhook)
    guild["webhook"]["avatar_url"] = arg
    await ctx.send("Updated the webhooks avatar to %s" % arg)
    save()


@bot.group(invoke_without_command=True, aliases=["sr"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def sticky_roles(ctx):
    """Display sticky roles"""
    guild = get_guild_config(ctx)
    if "sticky roles" in guild:
        v = ""
        for role in guild['sticky roles']:
            v += "\n%s" % ctx.guild.get_role(role).name
        if len(v) == 0:
            v = "\nNone"
    else:
        v = "\nNone"
    await ctx.send("Current sticky roles:%s" % v)


@sticky_roles.command(aliases=["add"])
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def add_sticky_role(ctx, role: discord.Role):
    """Add an sticky role"""
    guild = get_guild_config(ctx)
    if "sticky roles" not in guild:
        guild["sticky roles"] = []
    guild["sticky roles"].append(role.id)
    await ctx.send("Successfully added %s to the sticky roles!" % role.name)
    save()


@sticky_roles.command(aliases=["rem"])
@commands.check_any(commands.has_permissions(administrator=True), is_admin())
async def remove(ctx, role: discord.Role):
    """Remove a sticky role"""
    get_guild_config(ctx)["sticky roles"].remove(role.id)
    await ctx.send("Successfully removed %s from the sticky roles!" % role.name)
    save()


# Debug, done for manual saving
@bot.command(name="save")
@commands.is_owner()
async def save_command(ctx):
    """Owner command: Lets me manually save data"""
    save()


async def is_banned(guild, id: int):
    async for entry in guild.bans():
        if entry.user.id == id:
            reason = entry.reason if entry.reason is not None else "No reason given"
            return True, ", User is already banned. Reason: %s" % reason
    return False, ""


async def run_ban(ctx, id: int, *, reason: str = ""):
    try:
        info = await is_banned(ctx.guild, id)
        if not info[0]:
            target = await bot.fetch_user(id)
            await ctx.guild.ban(target, reason=reason)
            return True, target
        else:
            return False, info[1]
    except Exception as e:
        return False, e


async def _poll(ctx, id: int, *, reason: str = ""):
    try:
        target = await bot.fetch_user(id)
        return True, target
    except Exception as e:
        return False, e


@bot.command()
@commands.check_any(commands.has_permissions(administrator=True), is_mod(), is_admin())
async def ban(ctx, id: int, *, reason: str = ""):
    BAN.inc()
    target = await run_ban(ctx, id, reason=reason)
    if target[0]:
        await ctx.send(
            "Successfully banned <@{}> ({}#{})".format(target[1].id, target[1].name, target[1].discriminator))
    else:
        await ctx.send("Failed to ban %s" % target[1])


@bot.command()
@commands.check_any(commands.has_permissions(administrator=True), is_admin())
async def massban(ctx, *, reason: str = ""):
    def check(msg):
        return ctx.author.id == msg.author.id and ctx.channel.id == msg.channel.id

    MASS_BAN.inc()
    await ctx.send("Please send the IDs of users you want to ban, seperated by spaces")
    message = await bot.wait_for("message", check=check)
    identifiers = message.content.split(" ")

    def is_valid(s):
        try:
            int(s)
            return True
        except ValueError:
            return False

    temp = []
    for i in identifiers:
        if not is_valid(i):
            await ctx.send("%s is not an ID!" % i)
        else:
            temp.append(int(i))
    success = []
    failure = []
    for i in temp:
        result = await run_ban(ctx, i, reason=reason)
        if result[0]:
            success.append(str(result[1].id))
        else:
            failure.append(str(i))
    output = "{}/{} ID's banned\n\n Successful bans:\n {}\n\n Failed bans:\n {}".format(len(success),
                                                                                        len(success) + len(failure),
                                                                                        " ".join(success),
                                                                                        " ".join(failure))
    await send_long(ctx, output)


@bot.command()
@commands.is_owner()
async def masspong(ctx, *, reason: str = ""):
    """A debug tool for me to check the command"""

    def check(msg):
        return ctx.author.id == msg.author.id and ctx.channel.id == msg.channel.id

    await ctx.send("Please send the IDs of users you want to ping, seperated by spaces")
    message = await bot.wait_for("message", check=check)
    identifiers = message.content.split(" ")

    def is_valid(s):
        try:
            int(s)
            return True
        except ValueError:
            return False

    temp = []
    for i in identifiers:
        if not is_valid(i):
            await ctx.send("%s is not an ID!" % i)
        else:
            temp.append(int(i))
    success = []
    failure = []
    for i in temp:
        result = await _ban(ctx, i, reason=reason)
        if result[0]:
            success.append(str(result[1].id))
        else:
            failure.append(str(i))
    output = "{}/{} ID's banned\n\n Successful pings:\n {}\n\n Failed pings:\n {}".format(len(success),
                                                                                          len(success) + len(failure),
                                                                                          " ".join(success),
                                                                                          " ".join(failure))
    await send_long(ctx, output)


bot.run(os.environ['cephalobot_token'])

import discord
from discord.ext import commands
from discord import app_commands
import os
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

# Setup bot with intents
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix=[".v ", ".v"], intents=intents)

@bot.before_invoke
async def pro_respond_hook(ctx):
    original_send = ctx.send
    async def pro_send(*args, **kwargs):
        kwargs['reference'] = ctx.message
        kwargs.setdefault('mention_author', False)
        
        content = args[0] if args else kwargs.get('content')
        has_embed = kwargs.get('embed') or kwargs.get('embeds')
        has_file = kwargs.get('file') or kwargs.get('files')
        
        if content and not has_embed and not has_file:
            content_str = str(content)
            # Red color for errors/warnings, premium dark color for success/info
            color = 0xed4245 if "❌" in content_str or "Failed" in content_str or "Usage" in content_str else 0x2b2d31
            embed = discord.Embed(description=content_str, color=color)
            kwargs['embed'] = embed
            if 'content' in kwargs:
                del kwargs['content']
            return await original_send(**kwargs)
        return await original_send(*args, **kwargs)
    ctx.send = pro_send

DB_FILE = 'temp_voice.db'

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS temp_channels (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL
            )
        ''')
        await db.commit()

class RenameModal(discord.ui.Modal, title='Rename Channel'):
    name = discord.ui.TextInput(
        label='New Channel Name',
        placeholder='Enter new name...',
        min_length=1,
        max_length=100,
    )

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.channel.edit(name=self.name.value)
            await interaction.response.send_message(f"Channel renamed to **{self.name.value}**.", ephemeral=True)
        except discord.errors.HTTPException:
            await interaction.response.send_message("Failed to rename. You might be hitting Discord's rate limits.", ephemeral=True)

class LimitModal(discord.ui.Modal, title='Set User Limit'):
    limit = discord.ui.TextInput(
        label='User Limit (0 for unlimited)',
        placeholder='e.g. 5',
        min_length=1,
        max_length=2,
    )

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.limit.value)
            await self.channel.edit(user_limit=val)
            if val == 0:
                await interaction.response.send_message("User limit removed.", ephemeral=True)
            else:
                await interaction.response.send_message(f"User limit set to **{val}**.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
        except discord.errors.HTTPException:
            await interaction.response.send_message("Failed to change limit.", ephemeral=True)

class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Adding URL button manually since discord.py url buttons don't use callbacks
        self.add_item(discord.ui.Button(label="Rules", style=discord.ButtonStyle.link, url="https://discord.com/terms", row=3))

    async def _check_owner(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You are not in a voice channel.", ephemeral=True)
            return None, False
        
        channel = interaction.user.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message("You are not in a temporary voice channel.", ephemeral=True)
                return None, False
                
            if row[0] != interaction.user.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You do not own this temporary channel.", ephemeral=True)
                return channel, False
                
        return channel, True

    @discord.ui.button(emoji="🔐", style=discord.ButtonStyle.secondary, custom_id="vc_limit_set", row=0)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(LimitModal(channel))

    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vc_lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        default_role = interaction.guild.default_role
        if default_role in overrides:
            overrides[default_role].connect = False
        else:
            overrides[default_role] = discord.PermissionOverwrite(connect=False)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔒 Channel locked! Only people you invite can join.", ephemeral=True)

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vc_unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        default_role = interaction.guild.default_role
        if default_role in overrides:
            overrides[default_role].connect = True
        else:
            overrides[default_role] = discord.PermissionOverwrite(connect=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔓 Channel unlocked! Anyone can join now.", ephemeral=True)

    @discord.ui.button(emoji="👑", style=discord.ButtonStyle.secondary, custom_id="vc_claim", row=0)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You are not in a voice channel.", ephemeral=True)
            return
        channel = interaction.user.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            if not row:
                await interaction.response.send_message("Not a temporary channel.", ephemeral=True)
                return
            owner_id = row[0]
            if owner_id == interaction.user.id:
                await interaction.response.send_message("You already own this channel.", ephemeral=True)
                return
            owner = interaction.guild.get_member(owner_id)
            if owner and owner in channel.members:
                await interaction.response.send_message("The channel owner is still in the channel.", ephemeral=True)
                return
            await db.execute('UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?', (interaction.user.id, channel.id))
            await db.commit()
        await interaction.response.send_message("👑 You are now the owner of this channel.", ephemeral=True)

    @discord.ui.button(emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="vc_hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        default_role = interaction.guild.default_role
        if default_role in overrides:
            overrides[default_role].view_channel = False
        else:
            overrides[default_role] = discord.PermissionOverwrite(view_channel=False)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("👻 Channel hidden!", ephemeral=True)

    @discord.ui.button(emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="vc_unhide", row=1)
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        default_role = interaction.guild.default_role
        if default_role in overrides:
            overrides[default_role].view_channel = True
        else:
            overrides[default_role] = discord.PermissionOverwrite(view_channel=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("👁️ Channel is now visible!", ephemeral=True)

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="vc_limit_up", row=1)
    async def limit_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        new_limit = (channel.user_limit or 0) + 1
        if new_limit > 99: new_limit = 99
        await channel.edit(user_limit=new_limit)
        await interaction.response.send_message(f"Limit increased to {new_limit}.", ephemeral=True)

    @discord.ui.button(emoji="➖", style=discord.ButtonStyle.secondary, custom_id="vc_limit_down", row=1)
    async def limit_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        new_limit = (channel.user_limit or 0) - 1
        if new_limit < 0: new_limit = 0
        await channel.edit(user_limit=new_limit)
        await interaction.response.send_message(f"Limit decreased to {new_limit}.", ephemeral=True)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.secondary, custom_id="vc_delete", row=1)
    async def delete_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_message("Deleting channel...", ephemeral=True)
        await channel.delete()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel.id,))
            await db.commit()

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="vc_rename", row=1)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(RenameModal(channel))

    @discord.ui.button(label="Help / Guide", emoji="❓", style=discord.ButtonStyle.success, custom_id="vc_help", row=2)
    async def help_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        description = (
            "Need help managing your voice channel? Use the commands below to customize, control, and secure your VC with ease.\n\n"
            "✏️ | **name** : changes the name of the vc\n"
            "🔒 | **lock/unlock** : locks/unlocks the vc\n"
            "ℹ️ | **info/stats** : show information vc\n"
            "👥 | **limit** : sets the limit of the vc\n"
            "🔄 | **reset** : reset all permissions channel\n"
            "✅ | **permit** : gives a user permission to join the vc\n"
            "🌐 | **permall** : give perm current member your vc\n"
            "🎭 | **rpermit** : gives a join permission to role\n"
            "❌ | **reject** : removes a user permission to join the vc\n"
            "🔊 | **soundboard** : Toggles Soundboard on/off\n"
            "👻 | **hide/unhide** : unhides/hides the vc\n"
            "👑 | **owner** : shows the owner of the vc\n"
            "🔀 | **transfer** : Transfer Owner Channel\n"
            "🚩 | **claim** : claims the vc if the old owner is gone\n"
            "⏱️ | **slowmode** : changes the vc slowmode\n"
            "🎧 | **bitrate** : Going above 64 kbps may adversely affect\n"
            "🔇 | **tmute/tunmute** : Mute/Unmute a user from text your vc\n"
            "💬 | **status** : Set a status for your voice channel\n"
            "🔏 | **tlock/tunlock** : Lock/Unlock text chat in your vc\n"
            "🚫 | **bl [add/remove/clear]** : blacklist a specific user from your VC\n"
            "⚪ | **wl [add/remove/clear]** : whitelist a specific user to your VC\n"
            "🛡️ | **rwl [add/remove/clear]** : whitelist an entire role to your VC\n"
            "👔 | **cowner [list/add/remove/clear/permanent]** : assign a manager (co-owner) to your VC"
        )
        embed = discord.Embed(
            title="One Tap – Help Panel",
            description=description,
            color=0x2b2d31
        )
        embed.set_thumbnail(url="https://www.image2url.com/r2/default/gifs/1776733496700-23ee95e8-537e-4c91-a9fa-1b9c11e72f54.gif")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Music Bot", style=discord.ButtonStyle.primary, custom_id="vc_music", row=2)
    async def music_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Here is the link to add the music bot: https://example.com/music", ephemeral=True)

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(VoiceControlView()) # Register persistent view
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

@bot.event
async def on_voice_state_update(member, before, after):
    creator_channel_id = os.getenv("CREATOR_CHANNEL_ID")
    if not creator_channel_id:
        return
    
    try:
        creator_channel_id = int(creator_channel_id)
    except ValueError:
        return

    # Check if joined the creator channel
    if after.channel and after.channel.id == creator_channel_id:
        guild = member.guild
        category = after.channel.category
        
        channel_name = f"{member.display_name}'s Room"
        overrides = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(manage_channels=True, connect=True, move_members=True)
        }
        
        new_channel = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            overwrites=overrides
        )
        
        try:
            await member.move_to(new_channel)
        except discord.errors.HTTPException:
            await new_channel.delete()
            return

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT INTO temp_channels (channel_id, owner_id) VALUES (?, ?)', (new_channel.id, member.id))
            await db.commit()

        # Send the control panel
        embed = discord.Embed(
            title="🎙️ Your Exclusive Voice Channel",
            description=(
                f"Welcome, {member.mention}! Your private space has been created successfully.\n\n"
                f"**You are the Captain of this Ship ⚓**\n"
                f"You have full control over this channel. Use the interactive buttons below to manage access, or use our text commands (type `.v help` for the guide).\n\n"
                f"**Need assistance?** Reach out to **FLASH SS+** support."
            ),
            color=0x2b2d31 # Premium dark theme color
        )
        embed.set_author(name=f"{member.name}'s Channel", icon_url=member.display_avatar.url)
        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)
        embed.set_image(url="https://www.image2url.com/r2/default/gifs/1776734122792-630f8f36-b182-4d40-a86e-0fa8c63e594f.gif")
        embed.set_footer(text="Copyright 2026 • Developed by FLASH SS+ • All Rights Reserved")
        
        view = VoiceControlView()
        # Since voice channels can have messages, we send it there
        await new_channel.send(content=member.mention, embed=embed, view=view)

    # Check if left a temporary channel
    if before.channel and (not after.channel or before.channel.id != after.channel.id):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (before.channel.id,))
            row = await cursor.fetchone()
            
            if row:
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete()
                    except discord.errors.NotFound:
                        pass
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (before.channel.id,))
                    await db.commit()

# --- Slash Commands ---
class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_temp_channel_ctx(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You are not in a voice channel.")
            return None, None
            
        channel = ctx.author.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("You are not in a temporary voice channel.")
                return None, None
                
            is_owner = (row[0] == ctx.author.id)
            is_admin = ctx.author.guild_permissions.administrator
            is_co_owner = channel.permissions_for(ctx.author).manage_channels

            if not (is_owner or is_admin or is_co_owner):
                await ctx.send("You do not own or manage this temporary channel.")
                return None, None
                
        return channel, row[0]

    @commands.command(name="lock")
    async def lock_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role in overrides:
            overrides[default_role].connect = False
        else:
            overrides[default_role] = discord.PermissionOverwrite(connect=False)
        await channel.edit(overwrites=overrides)
        await ctx.send("🔒 Channel locked!")

    @commands.command(name="unlock")
    async def unlock_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role in overrides:
            overrides[default_role].connect = True
        else:
            overrides[default_role] = discord.PermissionOverwrite(connect=True)
        await channel.edit(overwrites=overrides)
        await ctx.send("🔓 Channel unlocked!")

    @commands.command(name="claim")
    async def claim_cmd(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("You are not in a voice channel.")
        channel = ctx.author.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            if not row:
                return await ctx.send("Not a temporary channel.")
            owner_id = row[0]
            if owner_id == ctx.author.id:
                return await ctx.send("You already own this channel.")
            owner = ctx.guild.get_member(owner_id)
            if owner and owner in channel.members:
                return await ctx.send("The channel owner is still in the channel.")
            await db.execute('UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?', (ctx.author.id, channel.id))
            await db.commit()
        await ctx.send("👑 You are now the owner of this channel.")

    @commands.command(name="owner")
    async def owner_cmd(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("You are not in a voice channel.")
        channel = ctx.author.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            if not row:
                return await ctx.send("Not a temporary channel.")
            owner = ctx.guild.get_member(row[0])
            name = owner.display_name if owner else "Unknown"
            await ctx.send(f"👑 The owner of this channel is **{name}**.")

    @commands.command(name="name")
    async def name_cmd(self, ctx: commands.Context, *, new_name: str):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        try:
            await channel.edit(name=new_name)
            await ctx.send(f"Channel renamed to **{new_name}**.")
        except discord.errors.HTTPException:
            await ctx.send("Failed to rename. You might be hitting Discord's rate limits.")

    @commands.command(name="limit")
    async def limit_cmd(self, ctx: commands.Context, limit: int):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        await channel.edit(user_limit=limit)
        await ctx.send(f"User limit set to **{limit}**." if limit > 0 else "User limit removed.")

    @commands.command(name="hide")
    async def hide_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role in overrides:
            overrides[default_role].view_channel = False
        else:
            overrides[default_role] = discord.PermissionOverwrite(view_channel=False)
        await channel.edit(overwrites=overrides)
        await ctx.send("👻 Channel hidden!")

    @commands.command(name="unhide")
    async def unhide_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role in overrides:
            overrides[default_role].view_channel = True
        else:
            overrides[default_role] = discord.PermissionOverwrite(view_channel=True)
        await channel.edit(overwrites=overrides)
        await ctx.send("👁️ Channel is now visible!")

    @commands.command(name="info", aliases=["stats"])
    async def info_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        embed = discord.Embed(title=f"ℹ️ Info for {channel.name}", color=0x2b2d31)
        embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000} kbps")
        embed.add_field(name="User Limit", value=f"{channel.user_limit if channel.user_limit else 'Unlimited'}")
        embed.add_field(name="Connected", value=f"{len(channel.members)}")
        await ctx.send(embed=embed)

    @commands.command(name="reset")
    async def reset_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if channel.category:
            await channel.edit(sync_permissions=True)
        overrides = channel.overwrites
        overrides[ctx.author] = discord.PermissionOverwrite(manage_channels=True, connect=True, move_members=True)
        await channel.edit(overwrites=overrides)
        await ctx.send("🔄 Channel permissions reset.")

    @commands.command(name="permit")
    async def permit_cmd(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        overrides[user] = discord.PermissionOverwrite(connect=True, view_channel=True)
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Granted {user.mention} permission to join.")

    @commands.command(name="permall")
    async def permall_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        for member in channel.members:
            if member != ctx.author:
                overrides[member] = discord.PermissionOverwrite(connect=True, view_channel=True)
        await channel.edit(overwrites=overrides)
        await ctx.send("🌐 Granted join permissions to all current members.")

    @commands.command(name="rpermit")
    async def rpermit_cmd(self, ctx: commands.Context, role: discord.Role):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        overrides[role] = discord.PermissionOverwrite(connect=True, view_channel=True)
        await channel.edit(overwrites=overrides)
        await ctx.send(f"🎭 Granted the role {role.name} permission to join.")

    @commands.command(name="reject")
    async def reject_cmd(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if user.id == owner_id:
            return await ctx.send("❌ You cannot reject the owner of the channel!")
        overrides = channel.overwrites
        overrides[user] = discord.PermissionOverwrite(connect=False)
        await channel.edit(overwrites=overrides)
        if user in channel.members:
            fallback_channel = ctx.guild.get_channel(1495973229024772136)
            if fallback_channel:
                try:
                    await user.move_to(fallback_channel)
                except discord.errors.HTTPException:
                    await user.move_to(None)
            else:
                await user.move_to(None)
        await ctx.send(f"❌ Rejected {user.mention}.")

    @commands.command(name="soundboard")
    async def soundboard_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        current = overrides.get(default_role)
        val = not current.use_soundboard if current and current.use_soundboard is not None else False
        if current:
            overrides[default_role].use_soundboard = val
        else:
            overrides[default_role] = discord.PermissionOverwrite(use_soundboard=val)
        await channel.edit(overwrites=overrides)
        await ctx.send(f"🔊 Soundboard is now {'enabled' if val else 'disabled'}.")

    @commands.command(name="transfer")
    async def transfer_cmd(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can transfer ownership.")
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?', (user.id, channel.id))
            await db.commit()
        overrides = channel.overwrites
        overrides[user] = discord.PermissionOverwrite(manage_channels=True, connect=True, move_members=True)
        await channel.edit(overwrites=overrides)
        await ctx.send(f"🔀 Transferred ownership to {user.mention}.")

    @commands.command(name="slowmode")
    async def slowmode_cmd(self, ctx: commands.Context, seconds: int):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        await channel.edit(slowmode_delay=seconds)
        await ctx.send(f"⏱️ Slowmode set to {seconds} seconds.")

    @commands.command(name="bitrate")
    async def bitrate_cmd(self, ctx: commands.Context, kbps: int):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        val = max(8000, min(kbps * 1000, ctx.guild.bitrate_limit))
        await channel.edit(bitrate=val)
        await ctx.send(f"🎧 Bitrate set to {val // 1000} kbps.")

    @commands.command(name="tmute")
    async def tmute_cmd(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if user.id == owner_id:
            return await ctx.send("❌ You cannot mute the owner of the channel!")
        overrides = channel.overwrites
        if user not in overrides:
            overrides[user] = discord.PermissionOverwrite()
        overrides[user].send_messages = False
        await channel.edit(overwrites=overrides)
        await ctx.send(f"🔇 {user.mention} is now text-muted.")

    @commands.command(name="tunmute")
    async def tunmute_cmd(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        if user not in overrides:
            overrides[user] = discord.PermissionOverwrite()
        overrides[user].send_messages = True
        await channel.edit(overwrites=overrides)
        await ctx.send(f"🔊 {user.mention} is now text-unmuted.")

    @commands.command(name="status")
    async def status_cmd(self, ctx: commands.Context, *, text: str = None):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        try:
            await channel.edit(status=text)
            await ctx.send(f"💬 Status set to: {text}")
        except discord.errors.HTTPException:
            await ctx.send("Status is not supported or rate limited.")

    @commands.command(name="tlock")
    async def tlock_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role not in overrides:
            overrides[default_role] = discord.PermissionOverwrite()
        overrides[default_role].send_messages = False
        await channel.edit(overwrites=overrides)
        await ctx.send("🔏 Text chat locked!")

    @commands.command(name="tunlock")
    async def tunlock_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        default_role = ctx.guild.default_role
        if default_role not in overrides:
            overrides[default_role] = discord.PermissionOverwrite()
        overrides[default_role].send_messages = True
        await channel.edit(overwrites=overrides)
        await ctx.send("🔓 Text chat unlocked!")

    @commands.group(name="bl", invoke_without_command=True)
    async def bl_cmd(self, ctx: commands.Context, user: discord.Member = None):
        if user: await self.bl_add(ctx, user)

    @bl_cmd.command(name="add")
    async def bl_add(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if user.id == owner_id:
            return await ctx.send("❌ You cannot blacklist the owner of the channel!")
        overrides = channel.overwrites
        if user not in overrides: overrides[user] = discord.PermissionOverwrite()
        overrides[user].connect = False
        overrides[user].view_channel = False
        await channel.edit(overwrites=overrides)
        if user in channel.members:
            fallback_channel = ctx.guild.get_channel(1495973229024772136)
            if fallback_channel:
                try:
                    await user.move_to(fallback_channel)
                except discord.errors.HTTPException:
                    await user.move_to(None)
            else:
                await user.move_to(None)
        await ctx.send(f"🚫 Blacklisted {user.mention}.")

    @bl_cmd.command(name="remove")
    async def bl_remove(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        if user in overrides:
            overrides[user].connect = None
            overrides[user].view_channel = None
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Removed blacklist for {user.mention}.")

    @bl_cmd.command(name="clear")
    async def bl_clear(self, ctx: commands.Context):
        await ctx.send("Clear command requires a database tracking update. Not fully implemented yet.")

    @commands.group(name="wl", invoke_without_command=True)
    async def wl_cmd(self, ctx: commands.Context, user: discord.Member = None):
        if user: await self.wl_add(ctx, user)

    @wl_cmd.command(name="add")
    async def wl_add(self, ctx: commands.Context, user: discord.Member):
        await self.permit_cmd(ctx, user)

    @wl_cmd.command(name="remove")
    async def wl_remove(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        if user in overrides:
            overrides[user].connect = None
            overrides[user].view_channel = None
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Removed whitelist for {user.mention}.")

    @wl_cmd.command(name="clear")
    async def wl_clear(self, ctx: commands.Context):
        await ctx.send("Clear command requires a database tracking update. Not fully implemented yet.")

    @commands.group(name="rwl", invoke_without_command=True)
    async def rwl_cmd(self, ctx: commands.Context, role: discord.Role = None):
        if role: await self.rwl_add(ctx, role)

    @rwl_cmd.command(name="add")
    async def rwl_add(self, ctx: commands.Context, role: discord.Role):
        await self.rpermit_cmd(ctx, role)

    @rwl_cmd.command(name="remove")
    async def rwl_remove(self, ctx: commands.Context, role: discord.Role):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        if role in overrides:
            overrides[role].connect = None
            overrides[role].view_channel = None
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Removed whitelist for {role.name}.")

    @rwl_cmd.command(name="clear")
    async def rwl_clear(self, ctx: commands.Context):
        await ctx.send("Clear command requires a database tracking update. Not fully implemented yet.")

    @commands.group(name="cowner", invoke_without_command=True)
    async def cowner_cmd(self, ctx: commands.Context, user: discord.Member = None):
        if user: await self.cowner_add(ctx, user)

    @cowner_cmd.command(name="add")
    async def cowner_add(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can manage Co-Owners.")
        if user.id == owner_id:
            return await ctx.send("❌ This user is already the owner of the channel!")
        overrides = channel.overwrites
        if user not in overrides: overrides[user] = discord.PermissionOverwrite()
        overrides[user].manage_channels = True
        overrides[user].connect = True
        await channel.edit(overwrites=overrides)
        await ctx.send(f"👔 Added {user.mention} as a Co-Owner.")

    @cowner_cmd.command(name="remove")
    async def cowner_remove(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can manage Co-Owners.")
        overrides = channel.overwrites
        if user in overrides:
            overrides[user].manage_channels = None
        await channel.edit(overwrites=overrides)
        await ctx.send(f"👔 Removed {user.mention} from Co-Owner.")

    @cowner_cmd.command(name="list")
    async def cowner_list(self, ctx: commands.Context):
        await ctx.send("List command requires a database tracking update. Not fully implemented yet.")

    @cowner_cmd.command(name="clear")
    async def cowner_clear(self, ctx: commands.Context):
        await ctx.send("Clear command requires a database tracking update. Not fully implemented yet.")

    @cowner_cmd.command(name="permanent")
    async def cowner_permanent(self, ctx: commands.Context):
        await ctx.send("Permanent command requires a database tracking update. Not fully implemented yet.")

async def setup_bot():
    await bot.add_cog(VoiceCog(bot))

@bot.event
async def setup_hook():
    await setup_bot()

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if token and token != 'your_discord_bot_token_here':
        bot.run(token)
    else:
        print("⚠️ Error: Please replace 'your_discord_bot_token_here' in your .env file with your actual Discord bot token.")

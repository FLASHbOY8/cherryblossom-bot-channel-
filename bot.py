import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
import asyncio
import aiosqlite
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# List of user IDs to DM (replace with actual Discord user IDs)
USER_ID_LIST = [123456789012345678, 987654321098765432]

# Message content to send to each user
DM_CONTENT = "Hello! This is an automated message from the Cherry Blossom bot."

# Setup bot with intents
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=[".v ", ".v"],
    intents=intents,
    activity=discord.Activity(type=discord.ActivityType.watching, name="🌸 Cherry Blossom | .v help"),
    status=discord.Status.online)

# Command to send DMs to a predefined list of users with rate limiting
@bot.command(name="send_dms")
async def send_dms(ctx):
    """Send a private message to each user in USER_ID_LIST with random delays to avoid rate limits."""
    await ctx.send("Starting DM broadcast...")
    for user_id in USER_ID_LIST:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(DM_CONTENT)
            print(f"[DM] Sent to {user_id}")
        except Exception as e:
            print(f"[DM] Failed to send to {user_id}: {e}")
        # Random delay between 5 and 10 seconds
        await asyncio.sleep(random.uniform(5, 10))
    await ctx.send("DM broadcast completed.")

# Remember to replace USER_ID_LIST with the target user IDs and set DM_CONTENT as desired.
# Bot token should be added at the bottom of this file (or use environment variable).
# Ensure the bot has the "Members" privileged intent enabled in the Discord developer portal.


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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS co_owners (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS blacklists (
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, owner_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS whitelists (
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, owner_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channels_created INTEGER DEFAULT 0,
                total_time_seconds INTEGER DEFAULT 0,
                last_joined TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '.v',
                default_channel_name TEXT DEFAULT '{user}''s Room',
                default_limit INTEGER DEFAULT 0,
                default_locked INTEGER DEFAULT 0,
                fallback_channel_id INTEGER DEFAULT 0
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
            await interaction.response.send_message(f"✅ Channel renamed to **{self.name.value}**.", ephemeral=True)
        except discord.errors.HTTPException:
            await interaction.response.send_message("❌ Failed to rename. Rate limited?", ephemeral=True)

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
            await interaction.response.send_message(f"✅ Limit set to **{val if val > 0 else 'Unlimited'}**.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

class SlowmodeModal(discord.ui.Modal, title='Set Slowmode'):
    seconds = discord.ui.TextInput(
        label='Slowmode Seconds (0 to disable)',
        placeholder='e.g. 5',
        min_length=1,
        max_length=5,
    )
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.seconds.value)
            await self.channel.edit(slowmode_delay=val)
            await interaction.response.send_message(f"⏱️ Slowmode set to **{val}** seconds.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid number.", ephemeral=True)

class BitrateModal(discord.ui.Modal, title='Set Bitrate'):
    kbps = discord.ui.TextInput(
        label='Bitrate in kbps (e.g. 64, 96, 128)',
        placeholder='64',
        min_length=1,
        max_length=3,
    )
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.kbps.value)
            limit = interaction.guild.bitrate_limit
            bitrate = max(8000, min(val * 1000, limit))
            await self.channel.edit(bitrate=bitrate)
            await interaction.response.send_message(f"🎧 Bitrate set to **{bitrate // 1000}** kbps.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid number.", ephemeral=True)

class StatusModal(discord.ui.Modal, title='Set Channel Status'):
    status = discord.ui.TextInput(
        label='Voice Channel Status',
        placeholder='Enter status text...',
        min_length=0,
        max_length=500,
        required=False
    )
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.channel.edit(status=self.status.value)
            await interaction.response.send_message(f"💬 Status updated.", ephemeral=True)
        except discord.errors.HTTPException:
            await interaction.response.send_message("❌ Failed to set status.", ephemeral=True)

class UserSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel, action: str):
        super().__init__(timeout=60)
        self.channel = channel
        self.action = action

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        user = select.values[0]
        if self.action == "permit":
            overrides = self.channel.overwrites
            overrides[user] = discord.PermissionOverwrite(connect=True, view_channel=True)
            await self.channel.edit(overwrites=overrides)
            await interaction.response.send_message(f"✅ Granted {user.mention} permission to join.", ephemeral=True)
        elif self.action == "reject":
            async with aiosqlite.connect(DB_FILE) as db:
                cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (self.channel.id,))
                row = await cursor.fetchone()
                if row and user.id == row[0]:
                    return await interaction.response.send_message("❌ You cannot reject the owner!", ephemeral=True)
            overrides = self.channel.overwrites
            overrides[user] = discord.PermissionOverwrite(connect=False)
            await self.channel.edit(overwrites=overrides)
            if user in self.channel.members:
                try: await user.move_to(None)
                except: pass
            await interaction.response.send_message(f"❌ Rejected {user.mention}.", ephemeral=True)
        elif self.action == "transfer":
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?', (user.id, self.channel.id))
                await db.commit()
            overwrites = self.channel.overwrites
            overwrites[user] = discord.PermissionOverwrite(connect=True, move_members=True)
            await self.channel.edit(overwrites=overwrites)
            await interaction.response.send_message(f"🔀 Transferred ownership to {user.mention}.", ephemeral=True)
        elif self.action == "cowner_add":
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('INSERT OR REPLACE INTO co_owners (channel_id, user_id) VALUES (?, ?)', (self.channel.id, user.id))
                await db.commit()
            overrides = self.channel.overwrites
            if user not in overrides: overrides[user] = discord.PermissionOverwrite()
            overrides[user].move_members = True
            await self.channel.edit(overwrites=overwrites)
            await interaction.response.send_message(f"👔 Added {user.mention} as a Co-Owner.", ephemeral=True)

class OwnerMenuView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=300)
        self.channel = channel

    @discord.ui.button(label="Transfer Ownership", emoji="🔀", style=discord.ButtonStyle.secondary)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select the new owner:", view=UserSelectView(self.channel, "transfer"), ephemeral=True)

    @discord.ui.button(label="Add Co-Owner", emoji="👔", style=discord.ButtonStyle.secondary)
    async def add_co_owner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select a user to make Co-Owner:", view=UserSelectView(self.channel, "cowner_add"), ephemeral=True)

    @discord.ui.button(label="List Co-Owners", emoji="📋", style=discord.ButtonStyle.secondary)
    async def list_co_owners(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM co_owners WHERE channel_id = ?', (self.channel.id,))
            rows = await cursor.fetchall()
        if not rows: return await interaction.response.send_message("No co-owners found.", ephemeral=True)
        mentions = [f"<@{row[0]}>" for row in rows]
        await interaction.response.send_message(f"👔 **Co-Owners:**\n" + "\n".join(mentions), ephemeral=True)

class InitialControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Control Panel", emoji="🎛️", style=discord.ButtonStyle.primary, custom_id="vc_open_panel")
    async def open_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (interaction.channel_id,))
            row = await cursor.fetchone()
            if not row:
                return await interaction.response.send_message("❌ Not a temporary channel.", ephemeral=True)
            
            is_owner = (row[0] == interaction.user.id)
            is_admin = interaction.user.guild_permissions.administrator
            cursor = await db.execute('SELECT 1 FROM co_owners WHERE channel_id = ? AND user_id = ?', (interaction.channel_id, interaction.user.id))
            is_co_owner = (await cursor.fetchone()) is not None
            
            if not (is_owner or is_admin or is_co_owner):
                return await interaction.response.send_message("❌ Only the owner or co-owners can open the control panel.", ephemeral=True)

        await interaction.response.edit_message(view=VoiceControlView())

class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _check_owner(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You are not in a voice channel.", ephemeral=True)
            return None, False
        
        channel = interaction.user.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message("❌ Not a temporary voice channel.", ephemeral=True)
                return None, False
                
            is_actual_owner = (row[0] == interaction.user.id)
            is_admin = interaction.user.guild_permissions.administrator
            
            # Check Co-Owner
            cursor = await db.execute('SELECT 1 FROM co_owners WHERE channel_id = ? AND user_id = ?', (channel.id, interaction.user.id))
            is_co_owner = (await cursor.fetchone()) is not None

            if not (is_actual_owner or is_admin or is_co_owner):
                await interaction.response.send_message("❌ You do not have permission to manage this channel.", ephemeral=True)
                return channel, False
                
        return channel, True

    # Row 0: General Control
    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vc_lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔒 Channel locked!", ephemeral=True)

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vc_unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(connect=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔓 Channel unlocked!", ephemeral=True)

    @discord.ui.button(emoji="👻", style=discord.ButtonStyle.secondary, custom_id="vc_hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("👻 Channel hidden!", ephemeral=True)

    @discord.ui.button(emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="vc_unhide", row=0)
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("👁️ Channel is now visible!", ephemeral=True)

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="vc_rename", row=0)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(RenameModal(channel))

    # Row 1: Limit Control
    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="vc_limit_up", row=1)
    async def limit_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        new_limit = min((channel.user_limit or 0) + 1, 99)
        await channel.edit(user_limit=new_limit)
        await interaction.response.send_message(f"➕ Limit increased to {new_limit}.", ephemeral=True)

    @discord.ui.button(emoji="➖", style=discord.ButtonStyle.secondary, custom_id="vc_limit_down", row=1)
    async def limit_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        new_limit = max((channel.user_limit or 0) - 1, 0)
        await channel.edit(user_limit=new_limit)
        await interaction.response.send_message(f"➖ Limit decreased to {new_limit}.", ephemeral=True)

    @discord.ui.button(emoji="👥", style=discord.ButtonStyle.secondary, custom_id="vc_limit_set", row=1)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(LimitModal(channel))

    @discord.ui.button(emoji="🚩", style=discord.ButtonStyle.secondary, custom_id="vc_claim", row=1)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You are not in a voice channel.", ephemeral=True)
        channel = interaction.user.voice.channel
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            row = await cursor.fetchone()
            if not row: return await interaction.response.send_message("❌ Not a temporary channel.", ephemeral=True)
            owner_id = row[0]
            if owner_id == interaction.user.id: return await interaction.response.send_message("✅ You already own this channel.", ephemeral=True)
            owner = interaction.guild.get_member(owner_id)
            if owner and owner in channel.members: return await interaction.response.send_message("❌ The owner is still present.", ephemeral=True)
            await db.execute('UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?', (interaction.user.id, channel.id))
            await db.commit()
        overwrites = channel.overwrites
        overwrites[interaction.user] = discord.PermissionOverwrite(connect=True, move_members=True)
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message("👑 You are now the owner!", ephemeral=True)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="vc_reset", row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        if channel.category: await channel.edit(sync_permissions=True)
        overwrites = channel.overwrites
        overwrites[interaction.user] = discord.PermissionOverwrite(connect=True, move_members=True)
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message("🔄 Permissions reset.", ephemeral=True)

    # Row 2: Access Control
    @discord.ui.button(emoji="✅", label="Permit", style=discord.ButtonStyle.secondary, custom_id="vc_permit", row=2)
    async def permit(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_message("Select a user to permit:", view=UserSelectView(channel, "permit"), ephemeral=True)

    @discord.ui.button(emoji="❌", label="Reject", style=discord.ButtonStyle.secondary, custom_id="vc_reject", row=2)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_message("Select a user to reject:", view=UserSelectView(channel, "reject"), ephemeral=True)

    @discord.ui.button(label="Back", emoji="🔙", style=discord.ButtonStyle.secondary, custom_id="vc_back", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_allowed = await self._check_owner(interaction)
        if not channel or not is_allowed: return
        await interaction.response.edit_message(view=InitialControlView())

    @discord.ui.button(emoji="👑", label="Owner", style=discord.ButtonStyle.secondary, custom_id="vc_owner_menu", row=2)
    async def owner_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_allowed = await self._check_owner(interaction)
        if not channel or not is_allowed: return
        embed = discord.Embed(title="👑 Owner Settings", description="Management options for your channel.", color=0x2b2d31)
        await interaction.response.send_message(embed=embed, view=OwnerMenuView(channel), ephemeral=True)

    @discord.ui.button(emoji="❓", style=discord.ButtonStyle.secondary, custom_id="vc_help", row=2)
    async def help_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        description = (
            "**Control Panel Guide**\n\n"
            "🔒/🔓 : Lock/Unlock VC\n"
            "👻/👁️ : Hide/Unhide VC\n"
            "✏️ : Rename Channel\n"
            "➕/➖/👥 : Manage User Limit\n"
            "✅/❌ : Permit/Reject User\n"
            "🔙 : Back to main button\n"
            "🔄 : Reset Permissions\n"
            "🔏/🔓 : Text Chat Lock/Unlock\n"
            "⏱️/🎧/💬 : Slowmode/Bitrate/Status\n"
            "🔊 : Toggle Soundboard\n"
            "🌐 : Permit All Members\n"
            "🔌 : Join/Leave Channel\n\n"
            "📜 **Rules**: Read in <#1426676905201106964>"
        )
        embed = discord.Embed(title="One Tap – Help Panel", description=description, color=0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 3: Text & Misc
    @discord.ui.button(emoji="🔏", style=discord.ButtonStyle.secondary, custom_id="vc_tlock", row=3)
    async def tlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(send_messages=False)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔏 Text chat locked!", ephemeral=True)

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vc_tunlock", row=3)
    async def tunlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(send_messages=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🔓 Text chat unlocked!", ephemeral=True)

    @discord.ui.button(emoji="⏱️", style=discord.ButtonStyle.secondary, custom_id="vc_slowmode", row=3)
    async def slowmode(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(SlowmodeModal(channel))

    @discord.ui.button(emoji="🎧", style=discord.ButtonStyle.secondary, custom_id="vc_bitrate", row=3)
    async def bitrate(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(BitrateModal(channel))

    @discord.ui.button(emoji="💬", style=discord.ButtonStyle.secondary, custom_id="vc_status", row=3)
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        await interaction.response.send_modal(StatusModal(channel))

    # Row 4: Extra Tools
    @discord.ui.button(emoji="🎸", style=discord.ButtonStyle.secondary, custom_id="vc_music", row=4)
    async def music_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice: return await interaction.response.send_message("❌ Join a VC first.", ephemeral=True)
        jockie = discord.utils.find(lambda m: "jockie music" in m.name.lower() and m.bot, interaction.guild.members)
        if not jockie: return await interaction.response.send_message("❌ Jockie Music bot not found.", ephemeral=True)
        try: await jockie.move_to(interaction.user.voice.channel)
        except: pass
        await interaction.response.send_message("🎸 Summoned Music Bot!", ephemeral=True)

    @discord.ui.button(emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id="vc_info", row=4)
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_allowed = await self._check_owner(interaction)
        if not channel: return
        embed = discord.Embed(title=f"ℹ️ {channel.name}", color=0x2b2d31)
        embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000} kbps")
        embed.add_field(name="Limit", value=f"{channel.user_limit or 'Unlimited'}")
        embed.add_field(name="Users", value=f"{len(channel.members)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="vc_soundboard", row=4)
    async def soundboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        curr = overrides.get(interaction.guild.default_role)
        val = not curr.use_soundboard if curr and curr.use_soundboard is not None else False
        overrides[interaction.guild.default_role] = discord.PermissionOverwrite(use_soundboard=val)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message(f"🔊 Soundboard {'enabled' if val else 'disabled'}.", ephemeral=True)

    @discord.ui.button(emoji="🌐", style=discord.ButtonStyle.secondary, custom_id="vc_permall", row=4)
    async def permall(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_owner = await self._check_owner(interaction)
        if not channel or not is_owner: return
        overrides = channel.overwrites
        for m in channel.members:
            if not m.bot: overrides[m] = discord.PermissionOverwrite(connect=True, view_channel=True)
        await channel.edit(overwrites=overrides)
        await interaction.response.send_message("🌐 Permitted all current members.", ephemeral=True)

    @discord.ui.button(emoji="🔌", style=discord.ButtonStyle.secondary, custom_id="vc_join", row=4)
    async def join_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, is_allowed = await self._check_owner(interaction)
        if not channel: return
        if interaction.guild.voice_client and interaction.guild.voice_client.channel == channel:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("🔌 Left channel.", ephemeral=True)
        else:
            await channel.connect()
            await interaction.response.send_message("🔌 Joined channel!", ephemeral=True)


@tasks.loop(hours=4)
async def send_server_stats():
    STATS_CHANNEL_ID = 1502478722794651768
    channel = bot.get_channel(STATS_CHANNEL_ID)
    if not channel:
        return
    guild = channel.guild
    
    total_members = guild.member_count
    voice_members = sum(len(vc.members) for vc in guild.voice_channels)
    boosts = guild.premium_subscription_count
    
    embed = discord.Embed(
        title="🌸 Cherry Blossom Stats",
        color=0x2b2d31
    )
    
    embed.add_field(name="👥 members :", value=f"〰️ {total_members}", inline=True)
    embed.add_field(name="🔊 voice :", value=f"〰️ {voice_members}", inline=True)
    embed.add_field(name="💎 boosts :", value=f"〰️ {boosts}", inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    now = datetime.now().strftime("%m/%d/%Y, %H:%M")
    embed.set_footer(text=f"Server Live Stats | {now}", icon_url=guild.icon.url if guild.icon else None)
    
    # We will fetch messages to see if we should edit the last one or send a new one
    # But the user asked to send it every 4 hours, so we send a new one.
    await channel.send(embed=embed)

@send_server_stats.before_loop
async def before_send_server_stats():
    await bot.wait_until_ready()

@tasks.loop(minutes=10)
async def send_temp_channel_reminders():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('SELECT channel_id FROM temp_channels')
        rows = await cursor.fetchall()
        for row in rows:
            channel = bot.get_channel(row[0])
            if channel:
                embed = discord.Embed(
                    description="Welcome to Cherry Blossom! 🌸\nIf you want any help, tap `.v help` or use the control buttons in your channel creation message.",
                    color=0x2b2d31
                )
                try:
                    await channel.send(embed=embed)
                except:
                    pass

@send_temp_channel_reminders.before_loop
async def before_send_temp_channel_reminders():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(VoiceControlView()) # Register persistent view
    bot.add_view(InitialControlView()) # Register persistent initial view
    if not send_server_stats.is_running():
        send_server_stats.start()
    if not send_temp_channel_reminders.is_running():
        send_temp_channel_reminders.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    
    # Auto-join the Creator Channel (Tap)
    creator_channel_id = os.getenv("CREATOR_CHANNEL_ID")
    if creator_channel_id and creator_channel_id.isdigit():
        channel = bot.get_channel(int(creator_channel_id))
        if channel and isinstance(channel, discord.VoiceChannel):
            if not channel.guild.voice_client:
                try:
                    await channel.connect()
                    print(f"Joined Creator Channel: {channel.name}")
                except Exception as e:
                    print(f"Failed to join Creator Channel: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    # Global voice blacklist - these users get moved to fallback channel immediately
    VOICE_BLACKLIST = set()
    FALLBACK_CHANNEL_ID = 1495973229024772136

    if member.id in VOICE_BLACKLIST and after.channel and after.channel.id != FALLBACK_CHANNEL_ID:
        fallback = member.guild.get_channel(FALLBACK_CHANNEL_ID)
        if fallback:
            try:
                await member.move_to(fallback)
            except discord.errors.HTTPException:
                await member.move_to(None)
        else:
            await member.move_to(None)
        return

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
            member: discord.PermissionOverwrite(connect=True, move_members=True)
        }
        
        # Hide from specific roles
        for role_id in [1426818689969291406, 1426676696899387636]:
            role = guild.get_role(role_id)
            if role:
                overrides[role] = discord.PermissionOverwrite(view_channel=False)

        
        new_channel = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            overwrites=overrides
        )
        
        try:
            await member.move_to(new_channel)
        except discord.errors.HTTPException:
            return

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT INTO temp_channels (channel_id, owner_id) VALUES (?, ?)', (new_channel.id, member.id))
            # Track user stats
            await db.execute('''
                INSERT INTO user_stats (guild_id, user_id, channels_created, last_joined)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    channels_created = channels_created + 1,
                    last_joined = ?
            ''', (guild.id, member.id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
            await db.commit()

        # Send the control panel
        embed = discord.Embed(
            title="🌸 Cherry Blossom – Professional sanctuary",
            description=(
                f"✨ Welcome to your private space, {member.mention}!\n\n"
                f"**Captain's Bridge ⚓**\n"
                f"You hold the keys to this room. Tap the **Control Panel** button below to access all management tools and settings.\n\n"
                f"🎀 *Need help? Use `.v help` or contact support.*"
            ),
            color=0x2b2d31 # Professional Dark Theme
        )
        embed.set_author(name=f"{member.name}'s Channel", icon_url=member.display_avatar.url)
        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)
        embed.set_image(url="https://www.image2url.com/r2/default/gifs/1776734122792-630f8f36-b182-4d40-a86e-0fa8c63e594f.gif")
        embed.set_footer(text="Copyright 2026 • Developed by FLASH SS+ • All Rights Reserved")
        
        view = InitialControlView()
        # Since voice channels can have messages, we send it there
        await new_channel.send(content=member.mention, embed=embed, view=view)

    # Auto-delete when everyone leaves the temporary channel
    if before.channel and (not after.channel or before.channel.id != after.channel.id):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT owner_id FROM temp_channels WHERE channel_id = ?', (before.channel.id,))
            row = await cursor.fetchone()
            
            if row:
                humans_left = [m for m in before.channel.members if not m.bot]
                if len(humans_left) == 0:
                    try:
                        await before.channel.delete()
                    except discord.errors.NotFound:
                        pass
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (before.channel.id,))
                    await db.execute('DELETE FROM co_owners WHERE channel_id = ?', (before.channel.id,))
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
                
            is_actual_owner = (row[0] == ctx.author.id)
            is_admin = ctx.author.guild_permissions.administrator
            is_co_owner = channel.permissions_for(ctx.author).move_members

            if not (is_actual_owner or is_admin or is_co_owner):
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
            
        # Update permissions
        overrides = channel.overwrites
        old_owner = ctx.guild.get_member(owner_id)
        if old_owner and old_owner in overrides:
            overrides[old_owner].move_members = None
            
        overrides[ctx.author] = discord.PermissionOverwrite(connect=True, move_members=True)
        await channel.edit(overwrites=overrides)
        
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
        overrides[ctx.author] = discord.PermissionOverwrite(connect=True, move_members=True)
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
        # Remove old owner's powers
        old_owner = ctx.author
        if old_owner in overrides:
            overrides[old_owner].move_members = None
            
        # Give new owner powers
        overrides[user] = discord.PermissionOverwrite(connect=True, move_members=True)
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
        # Save to DB
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT OR REPLACE INTO blacklists (guild_id, owner_id, user_id) VALUES (?, ?, ?)', (ctx.guild.id, owner_id, user.id))
            await db.commit()
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
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('DELETE FROM blacklists WHERE guild_id = ? AND owner_id = ? AND user_id = ?', (ctx.guild.id, owner_id, user.id))
            await db.commit()
        await ctx.send(f"✅ Removed blacklist for {user.mention}.")

    @bl_cmd.command(name="clear")
    async def bl_clear(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can clear the blacklist.")
        # Remove all blacklist overrides from channel
        overrides = channel.overwrites
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM blacklists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            rows = await cursor.fetchall()
            for row in rows:
                member = ctx.guild.get_member(row[0])
                if member and member in overrides:
                    overrides[member].connect = None
                    overrides[member].view_channel = None
            await db.execute('DELETE FROM blacklists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            await db.commit()
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Cleared all blacklisted users ({len(rows)}).")

    @commands.group(name="wl", invoke_without_command=True)
    async def wl_cmd(self, ctx: commands.Context, user: discord.Member = None):
        if user: await self.wl_add(ctx, user)

    @wl_cmd.command(name="add")
    async def wl_add(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        overrides[user] = discord.PermissionOverwrite(connect=True, view_channel=True)
        await channel.edit(overwrites=overrides)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT OR REPLACE INTO whitelists (guild_id, owner_id, user_id) VALUES (?, ?, ?)', (ctx.guild.id, owner_id, user.id))
            await db.commit()
        await ctx.send(f"✅ Whitelisted {user.mention}.")

    @wl_cmd.command(name="remove")
    async def wl_remove(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        overrides = channel.overwrites
        if user in overrides:
            overrides[user].connect = None
            overrides[user].view_channel = None
        await channel.edit(overwrites=overrides)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('DELETE FROM whitelists WHERE guild_id = ? AND owner_id = ? AND user_id = ?', (ctx.guild.id, owner_id, user.id))
            await db.commit()
        await ctx.send(f"✅ Removed whitelist for {user.mention}.")

    @wl_cmd.command(name="clear")
    async def wl_clear(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can clear the whitelist.")
        overrides = channel.overwrites
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM whitelists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            rows = await cursor.fetchall()
            for row in rows:
                member = ctx.guild.get_member(row[0])
                if member and member in overrides:
                    overrides[member].connect = None
                    overrides[member].view_channel = None
            await db.execute('DELETE FROM whitelists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            await db.commit()
        await channel.edit(overwrites=overrides)
        await ctx.send(f"✅ Cleared all whitelisted users ({len(rows)}).")

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
        overrides[user].move_members = True
        overrides[user].mute_members = True
        overrides[user].connect = True
        await channel.edit(overwrites=overrides)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT OR REPLACE INTO co_owners (channel_id, user_id) VALUES (?, ?)', (channel.id, user.id))
            await db.commit()
        await ctx.send(f"👔 Added {user.mention} as a Co-Owner.")

    @cowner_cmd.command(name="remove")
    async def cowner_remove(self, ctx: commands.Context, user: discord.Member):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can manage Co-Owners.")
        overrides = channel.overwrites
        if user in overrides:
            overrides[user].move_members = None
            overrides[user].mute_members = None
        await channel.edit(overwrites=overrides)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('DELETE FROM co_owners WHERE channel_id = ? AND user_id = ?', (channel.id, user.id))
            await db.commit()
        await ctx.send(f"👔 Removed {user.mention} from Co-Owner.")

    @cowner_cmd.command(name="list")
    async def cowner_list(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM co_owners WHERE channel_id = ?', (channel.id,))
            rows = await cursor.fetchall()
        if not rows:
            return await ctx.send("👔 No co-owners for this channel.")
        names = []
        for row in rows:
            member = ctx.guild.get_member(row[0])
            names.append(member.mention if member else f"Unknown ({row[0]})")
        embed = discord.Embed(title="👔 Co-Owners", description="\n".join(names), color=0x2b2d31)
        await ctx.send(embed=embed)

    @cowner_cmd.command(name="clear")
    async def cowner_clear(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only the channel owner can clear co-owners.")
        overrides = channel.overwrites
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM co_owners WHERE channel_id = ?', (channel.id,))
            rows = await cursor.fetchall()
            for row in rows:
                member = ctx.guild.get_member(row[0])
                if member and member in overrides:
                    overrides[member].move_members = None
                    overrides[member].mute_members = None
            await db.execute('DELETE FROM co_owners WHERE channel_id = ?', (channel.id,))
            await db.commit()
        await channel.edit(overwrites=overrides)
        await ctx.send(f"👔 Cleared all co-owners ({len(rows)}).")

    @commands.command(name="mystats")
    async def mystats_cmd(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT channels_created, total_time_seconds, last_joined FROM user_stats WHERE guild_id = ? AND user_id = ?', (ctx.guild.id, ctx.author.id))
            row = await cursor.fetchone()
        if not row:
            return await ctx.send("📊 No stats found for you yet. Create a voice channel first!")
        channels_created = row[0]
        last_joined = row[2] or "Never"
        embed = discord.Embed(title="📊 Your Voice Stats", color=0x2b2d31)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="🎙️ Channels Created", value=f"**{channels_created}**", inline=True)
        embed.add_field(name="📅 Last Active", value=f"**{last_joined[:10]}**", inline=True)
        embed.set_footer(text="Cherry Blossom • Voice Stats")
        await ctx.send(embed=embed)

    @commands.command(name="bllist")
    async def bllist_cmd(self, ctx: commands.Context):
        """Shows your personal blacklist across all channels."""
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM blacklists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            rows = await cursor.fetchall()
        if not rows:
            return await ctx.send("🚫 No blacklisted users.")
        names = []
        for row in rows:
            member = ctx.guild.get_member(row[0])
            names.append(member.mention if member else f"Unknown ({row[0]})")
        embed = discord.Embed(title="🚫 Blacklisted Users", description="\n".join(names), color=0xed4245)
        await ctx.send(embed=embed)

    @commands.command(name="wllist")
    async def wllist_cmd(self, ctx: commands.Context):
        """Shows your whitelist for this channel."""
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute('SELECT user_id FROM whitelists WHERE guild_id = ? AND owner_id = ?', (ctx.guild.id, owner_id))
            rows = await cursor.fetchall()
        if not rows:
            return await ctx.send("⚪ No whitelisted users.")
        names = []
        for row in rows:
            member = ctx.guild.get_member(row[0])
            names.append(member.mention if member else f"Unknown ({row[0]})")
        embed = discord.Embed(title="⚪ Whitelisted Users", description="\n".join(names), color=0x2b2d31)
        await ctx.send(embed=embed)

    # --- Fun / Interaction Commands ---

    KISS_GIFS = [
        "https://www.image2url.com/r2/default/gifs/1778615807420-6a1da0e2-3ebb-4f96-8dfc-6594a31e36ed.gif",
        "https://www.image2url.com/r2/default/gifs/1778615915225-73aa3788-7bb8-431b-9ea8-bc36786b5a72.gif",
        "https://www.image2url.com/r2/default/gifs/1778616016553-2c90deaf-20cd-45cd-bb4c-02f949882134.gif",
    ]

    FUCK_GIFS = [
        "", # Placeholder - replace with actual gifs
    ]

    @commands.command(name="kiss")
    async def kiss_cmd(self, ctx: commands.Context, target: discord.Member = None):
        """Kiss another user with a random anime GIF."""
        if not target:
            return await ctx.send("❌ Usage: `.v kiss @user`")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You can't kiss yourself!")

        gif = random.choice(self.KISS_GIFS)

        embed = discord.Embed(
            description=f"{target.mention} you have been kissed by {ctx.author.mention} 💋",
            color=0x2b2d31
        )
        embed.set_image(url=gif)
        embed.set_footer(text=f"Requested By {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.command(name="fuck")
    async def fuck_cmd(self, ctx: commands.Context, target: discord.Member = None):
        """Express your frustration towards another user with a random anime GIF."""
        if not target:
            return await ctx.send("❌ Usage: `.v fuck @user`")
        if target.id == ctx.author.id:
            return await ctx.send("❌ You can't do that to yourself!")

        gif = random.choice(self.FUCK_GIFS)

        embed = discord.Embed(
            description=f"🖕 {ctx.author.mention} says **FUCK YOU** to {target.mention}!",
            color=0xed4245 # Red for frustration
        )
        embed.set_image(url=gif)
        embed.set_footer(text=f"Requested By {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.command(name="join")
    async def join_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        
        if ctx.guild.voice_client:
            if ctx.guild.voice_client.channel == channel:
                return await ctx.send("❌ I'm already in your voice channel!")
            await ctx.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send("✅ Successfully joined your voice channel!")

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def leave_cmd(self, ctx: commands.Context):
        channel, owner_id = await self.get_temp_channel_ctx(ctx)
        if not channel: return
        
        if not ctx.guild.voice_client:
            return await ctx.send("❌ I'm not in any voice channel.")
            
        if ctx.guild.voice_client.channel != channel:
            return await ctx.send("❌ I'm not in your voice channel.")
            
        await ctx.guild.voice_client.disconnect()
        await ctx.send("👋 Successfully left your voice channel.")

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

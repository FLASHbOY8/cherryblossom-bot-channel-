<p align="center">
  <img src="https://img.shields.io/badge/discord.py-2.7+-blue?style=for-the-badge&logo=discord&logoColor=white" />
  <img src="https://img.shields.io/badge/python-3.10+-yellow?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" />
</p>

<h1 align="center">🌸 CherryBlossom Bot</h1>
<p align="center">
  <b>A feature-rich Discord voice channel management bot.</b><br>
  Create temporary "One Tap" voice channels with full ownership controls, interactive button panels, and premium-styled responses.
</p>

---

## ✨ Features

| Category | Feature | Description |
|----------|---------|-------------|
| 🎙️ **One Tap** | Auto-create VCs | Users join a "Creator Channel" and instantly get their own private voice channel |
| 🎛️ **Control Panel** | Interactive Buttons | Lock, unlock, hide, rename, claim, and more — all from a sleek button panel |
| 👑 **Ownership** | Claim & Transfer | Full ownership system with claim, transfer, and co-owner management |
| 👔 **Co-Owners** | Shared Management | Assign co-owners who can manage the channel (but can't delete it!) |
| 🚫 **Moderation** | Blacklist / Whitelist | Granular user & role-based access control |
| 🎸 **Music** | Summon Muziq | One-click button to summon Jockie Music into your voice channel |
| 💎 **Pro Responses** | Styled Embeds | Every command response is wrapped in a premium dark-themed embed |
| 🔒 **Security** | Owner Immunity | The primary owner is immune to moderation actions from co-owners |
| 💾 **Database** | Persistent Storage | SQLite-powered storage for user stats, persistent blacklists, and whitelists |
| 📩 **Mass DM** | Automated Messaging | Secure, rate-limited broadcast messaging with clean delivery logic |
| 🎨 **Anime UI** | Premium Aesthetics | Vibrant, role-coded interactive buttons with Cherry Blossom Pink themes |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- A **Discord Bot** with the following intents enabled in the [Developer Portal](https://discord.com/developers/applications):
  - ✅ Server Members Intent
  - ✅ Message Content Intent
  - ✅ Presence Intent (optional)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/FLASHbOY8/cherryblossom-bot-channel-.git
cd cherryblossom-bot-channel-

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and add your bot token + creator channel ID
nano .env

# 5. Run the bot
python bot.py
```

### Configuration

Edit the `.env` file with your values:

```env
DISCORD_TOKEN=your_discord_bot_token_here
CREATOR_CHANNEL_ID=your_creator_voice_channel_id_here
```

| Variable | Description |
|----------|-------------|
| `DISCORD_TOKEN` | Your bot token from the Discord Developer Portal |
| `CREATOR_CHANNEL_ID` | The ID of the voice channel users join to create their own VC |

> 💡 **How to get a Channel ID:** Enable Developer Mode in Discord settings, then right-click the channel → "Copy Channel ID".

---

## 📋 Commands

All commands use the prefix `.v`

### 🛠️ General Customization

| Command | Description |
|---------|-------------|
| `.v name <text>` | Changes the name of the VC |
| `.v limit <number>` | Sets the max users allowed |
| `.v slowmode <seconds>` | Sets slowmode for the text chat |
| `.v bitrate <kbps>` | Adjusts audio quality |
| `.v status <text>` | Sets a custom status message |

### 🔒 Privacy & Access

| Command | Description |
|---------|-------------|
| `.v lock` / `.v unlock` | Prevents / allows users from joining |
| `.v hide` / `.v unhide` | Makes the VC invisible / visible |
| `.v permit @user` | Gives a user permission to join |
| `.v reject @user` | Removes a user's access (moves them out) |
| `.v permall` | Permits all current members |
| `.v rpermit @role` | Gives an entire role access |

### 👑 Ownership

| Command | Description |
|---------|-------------|
| `.v owner` | Shows who owns the channel |
| `.v claim` | Claims the VC if the owner has left |
| `.v transfer @user` | Transfers ownership to another user |
| `.v cowner @user` | Adds a co-owner |
| `.v cowner remove @user` | Removes a co-owner |

### 🔇 Text Moderation

| Command | Description |
|---------|-------------|
| `.v tmute @user` | Mutes a user from the VC text chat |
| `.v tunmute @user` | Unmutes a user |
| `.v tlock` / `.v tunlock` | Locks / unlocks the text chat for everyone |

### 🚫 Blacklist & Whitelist

| Command | Description |
|---------|-------------|
| `.v bl @user` | Blacklists a user from your VC |
| `.v bl remove @user` | Removes a user from the blacklist |
| `.v wl @user` | Whitelists a user to your VC |
| `.v wl remove @user` | Removes a user from the whitelist |
| `.v rwl @role` | Whitelists an entire role |

### 🔧 Utilities

| Command | Description |
|---------|-------------|
| `.v info` | Shows channel statistics |
| `.v mystats` | Shows your voice channel creation statistics |
| `.v reset` | Resets all channel permissions |
| `.v soundboard` | Toggles soundboard on/off |
| `.v join` | Bot joins your voice channel |
| `.v leave` | Bot leaves your voice channel |
| `.v bllist` | Displays your active blacklist |
| `.v wllist` | Displays your active whitelist |

---

## 🎛️ Button Panel

When a user creates a voice channel, they receive an interactive control panel with these buttons:

| Button | Function |
|--------|----------|
| 🔐 | Set user limit |
| 🔒 / 🔓 | Lock / Unlock |
| 👑 | Claim channel |
| 🚫 / 👁️ | Hide / Unhide |
| ➕ / ➖ | Increase / Decrease limit |
| 👑 Owner | Owner-only menu |
| ✏️ | Rename channel |
| ❓ Help | Full command guide |
| 📜 Rules | Server rules link |
| 🎸 Summon Muziq | Summon Jockie Music bot |

---

## 🏗️ Project Structure

```
cherryblossom-bot-channel-/
├── bot.py              # Main bot logic & all commands
├── requirements.txt    # Python dependencies
├── .env                # Environment variables (not tracked)
├── .env.example        # Template for environment variables
├── .gitignore          # Git ignore rules
├── temp_voice.db       # SQLite database (auto-created)
└── README.md           # This file
```

---

## 🛡️ Security Notes

- **Never** commit your `.env` file or share your bot token publicly.
- The `.gitignore` is configured to protect sensitive files.
- If your token is ever exposed, **reset it immediately** in the [Discord Developer Portal](https://discord.com/developers/applications).

---

## 📝 License

This project is open source and available under the [MIT License](LICENSE).

---

<p align="center">
  <b>Developed with ❤️ by FLASH SS+</b><br>
  Copyright 2026 • All Rights Reserved
</p>

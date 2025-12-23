import discord
from discord import app_commands, guild
from discord.app_commands.commands import describe
from discord.ext import commands
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import requests
from datetime import datetime 

load_dotenv()

token = os.getenv('token')
serverid_STR = os.getenv('serverid')
mongouri = os.getenv('mongouri', 'mongodb://localhost:27017/codejam')

if not token:
    print('ERROR: token is not set in .env file')
    exit(1)

if not serverid_STR:
    print('ERROR: serverid is not set in .env file')
    exit(1)

try:
    serverid = int(serverid_STR)
except ValueError:
    print(f'ERROR: serverid must be a number, got: {serverid_STR}')
    print('Make sure you replaced "your_server_id_here" with your actual server ID')
    exit(1)

if not mongouri:
    print('ERROR: MongoDB connection string is undefined')
    exit(1)

mongo_client = AsyncIOMotorClient(mongouri)
db = mongo_client.codejam
roles_collection = db.roles
team_members_collection = db.team_members  

intents = discord.Intents.default()
intents.members = True  

intents.message_content = True  

bot = commands.Bot(command_prefix='/', intents=intents)

async def check_permission(interaction: discord.Interaction) -> bool:
    return (interaction.user.guild_permissions.administrator or 
            any(role.name in ["CT25", "CT26"] for role in interaction.user.roles))

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    guild = bot.get_guild(serverid)

    if not guild:
        print(f'ERROR: Bot is not in guild {serverid}')
        print('Please invite the bot to your server using the OAuth2 URL with bot + applications.commands scopes')
        return

    print(f'Bot is in guild: {guild.name}')
    print(f'Guild has {guild.member_count} members')

    print('Syncing commands...')
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=serverid))
        print(f'✓ Successfully synced {len(synced)} command(s) to guild {serverid}')
        print('Commands available:')
        for cmd in synced:
            print(f'  - /{cmd.name}')
        print('\nBot is ready! Type / in Discord to see slash commands!')
    except discord.Forbidden as e:
        print(f'ERROR: Missing permissions to sync commands: {e}')
        print('Please re-invite the bot with "applications.commands" scope enabled')
        print('Go to Discord Developer Portal → OAuth2 → URL Generator')
        print('Check both "bot" and "applications.commands" scopes')
    except Exception as e:
        print(f'Error syncing commands: {e}')
        import traceback
        traceback.print_exc()

@bot.event
async def on_member_join(member):
    print(f'New member joined: {member.name}')

def get_commits(link: str):
    GITHUB_TOKEN=os.getenv("PAT")
    comps=link.split("/")
    owner=comps[-2] 
    repo= comps[-1]
    COMMIT_URL=f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=15"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
    }
    response = requests.get(COMMIT_URL, headers=headers)
    try:
        response.raise_for_status()
    except:
        return []
    return response.json()

def check_timestamps(link: str):
    commits=get_commits(link)
    if not commits:
        return 0
    count=0 
    headCommitTime=datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
    limit= datetime.fromisoformat("2025-12-23T14:30:00+00:00")
    if(headCommitTime>limit):
        for commit in commits:
            time=commit["commit"]["committer"]["date"].replace("Z", "+00:00")
            if(datetime.fromisoformat(time)>limit):
                count+=1
        return count
    else:
        return 0
    
@bot.tree.command(name="githubtimestamp", description="Mentions all teams who committed after deadline", guild=discord.Object(id=serverid))
async def githubtimestamp(interaction: discord.Interaction):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return

    allTeams= await roles_collection.find({}).to_list(length=100)
    try:
        if not allTeams:
            await interaction.response.send_message("No teams found in the database.")
            return
        
        repos={}

        for each in allTeams:
            repo = each.get('githubRepo', '')
            name= each.get('name')
            if repo:
                repos[name]=repo

        defaulters=[]

        for team in repos.keys():
            count = await asyncio.to_thread(check_timestamps, repos[team])
            if(count):
                defaulters.append(team+" "+"-"+" "+str(count))

        embed = discord.Embed(
            title="Defaulters",
            description="\n".join(defaulters)
        )

        await interaction.response.send_message(embed=embed)
    except Exception as error:
            print(f'Error fetching team list: {error}')
            await interaction.response.send_message("An error occurred while fetching the team list.")

@bot.tree.command(name="createteam", description="Create a new team with role and data", guild=discord.Object(id=serverid))
@app_commands.describe(
    name="Name of the team",
    color="Color name (red, blue, green, purple, orange, etc.) or hex code (#ff6a00) - optional",
    github_repo="The GitHub repository associated with the team - optional",
    github_usernames="Comma-separated list of GitHub usernames - optional",
    status="Status of the team - optional"
)
async def createteam(interaction: discord.Interaction, name: str, color: str = None, github_repo: str = None, github_usernames: str = None, status: str = None):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    existing_role = discord.utils.get(guild.roles, name=name)
    if existing_role:
        await interaction.followup.send(f'The role "{name}" already exists!', ephemeral=True)
        return

    role_color = discord.Color.default()
    if color:
        color_lower = color.lower().replace(' ', '_').replace('-', '_')

        color_map = {
            'red': discord.Color.red(),
            'dark_red': discord.Color.dark_red(),
            'green': discord.Color.green(),
            'dark_green': discord.Color.dark_green(),
            'blue': discord.Color.blue(),
            'dark_blue': discord.Color.dark_blue(),
            'purple': discord.Color.purple(),
            'dark_purple': discord.Color.dark_purple(),
            'magenta': discord.Color.magenta(),
            'dark_magenta': discord.Color.dark_magenta(),
            'orange': discord.Color.orange(),
            'dark_orange': discord.Color.dark_orange(),
            'gold': discord.Color.gold(),
            'yellow': discord.Color.gold(),
            'teal': discord.Color.teal(),
            'dark_teal': discord.Color.dark_teal(),
            'light_gray': discord.Color.light_grey(),
            'light_grey': discord.Color.light_grey(),
            'lighter_gray': discord.Color.lighter_grey(),
            'lighter_grey': discord.Color.lighter_grey(),
            'dark_gray': discord.Color.dark_grey(),
            'dark_grey': discord.Color.dark_grey(),
            'darker_gray': discord.Color.darker_grey(),
            'darker_grey': discord.Color.darker_grey(),
            'blurple': discord.Color.blurple(),
            'greyple': discord.Color.greyple(),
            'pink': discord.Color.from_rgb(255, 105, 180),
            'light_blue': discord.Color.from_rgb(135, 206, 250),
            'light_green': discord.Color.from_rgb(144, 238, 144),
            'light_purple': discord.Color.from_rgb(216, 191, 216),
            'light_orange': discord.Color.from_rgb(255, 200, 124),
        }

        if color_lower in color_map:
            role_color = color_map[color_lower]
        else:

            try:
                color_hex = color.lstrip('#')
                role_color = discord.Color(int(color_hex, 16))
            except ValueError:
                available_colors = ', '.join(['red', 'blue', 'green', 'purple', 'orange', 'pink', 'gold', 'teal', 'light blue', 'light green', 'dark blue', 'dark green'])
                await interaction.followup.send(
                    f"Invalid color. Use a color name ({available_colors}) or hex code (#ff6a00)", 
                    ephemeral=True
                )
                return

    try:
        new_role = await guild.create_role(
            name=name,
            color=role_color,
            mentionable=True,
            reason=f"Team role created by {interaction.user.name}"
        )
        
        usernames_list = [username.strip() for username in github_usernames.split(',')] if github_usernames else []
        role_data = {
            "name": name,
            "githubRepo": github_repo or '',
            "githubUsernames": usernames_list,
            "status": status or ''
        }
        await roles_collection.insert_one(role_data)
        
        await interaction.followup.send(f'✓ Successfully created team "{name}" with role and data!')
    except discord.Forbidden:
        await interaction.followup.send("I don't have permission to create roles. Please check my role permissions.", ephemeral=True)
    except Exception as e:
        print(f'Error creating team: {e}')
        await interaction.followup.send(f"An error occurred while creating the team: {e}", ephemeral=True)

@bot.tree.command(name="setup", description="Bulk setup operations for teams", guild=discord.Object(id=serverid))
@app_commands.describe(
    action="What to setup: channels, roles, or both"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Channels (text & voice)", value="channels"),
    app_commands.Choice(name="Roles (assign to members)", value="roles"),
    app_commands.Choice(name="Both (channels & roles)", value="both")
])
async def setup(interaction: discord.Interaction, action: app_commands.Choice[str]):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    action_value = action.value

    if action_value in ["channels", "both"]:
        await setup_channels(interaction, guild)
    
    if action_value in ["roles", "both"]:
        await setup_roles(interaction, guild)

async def setup_channels(interaction: discord.Interaction, guild: discord.Guild):
    category = discord.utils.get(guild.categories, name="CodeJam-v6")
    if not category:
        try:
            category = await guild.create_category("CodeJam-v6")
            await interaction.followup.send("✓ Created category 'CodeJam-v6'")
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create categories.")
            return

    ct25_role = discord.utils.get(guild.roles, name="CT25")
    ct26_role = discord.utils.get(guild.roles, name="CT26")

    try:
        all_teams = await roles_collection.find({}).to_list(length=100)
    except Exception as e:
        await interaction.followup.send(f"Error fetching teams from database: {e}")
        return

    if not all_teams:
        await interaction.followup.send("No teams found in database.")
        returnt

    text_created = 0
    text_updated = 0
    text_skipped = 0
    voice_created = 0
    voice_updated = 0
    voice_skipped = 0

    for team_data in all_teams:
        team_name = team_data['name']

        team_role = discord.utils.get(guild.roles, name=team_name)
        if not team_role:
            print(f"Role '{team_name}' not found, skipping channel creation")
            continue

        channel_name = team_name.lower().replace(' ', '-')

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            team_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True, connect=True, speak=True)
        }

        if ct25_role:
            overwrites[ct25_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True, connect=True, speak=True)
        if ct26_role:
            overwrites[ct26_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True, connect=True, speak=True)

        existing_text = discord.utils.get(category.text_channels, name=channel_name)

        if existing_text:

            needs_update = len(existing_text.overwrites) != len(overwrites)

            if needs_update:
                try:
                    await existing_text.edit(overwrites=overwrites)
                    text_updated += 1
                except Exception as e:
                    print(f"Error updating text permissions for {channel_name}: {e}")
            else:
                text_skipped += 1
        else:

            try:
                await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Team text channel created by {interaction.user.name}"
                )
                text_created += 1
                print(f"Created text channel: #{channel_name}")
            except Exception as e:
                print(f"Error creating text channel for {team_name}: {e}")

        voice_channel_name = f"{team_name} Voice"
        existing_voice = discord.utils.get(category.voice_channels, name=voice_channel_name)

        if existing_voice:

            needs_update = len(existing_voice.overwrites) != len(overwrites)

            if needs_update:
                try:
                    await existing_voice.edit(overwrites=overwrites)
                    voice_updated += 1
                except Exception as e:
                    print(f"Error updating voice permissions for {voice_channel_name}: {e}")
            else:
                voice_skipped += 1
        else:

            try:
                await guild.create_voice_channel(
                    name=voice_channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Team voice channel created by {interaction.user.name}"
                )
                voice_created += 1
                print(f"Created voice channel: {voice_channel_name}")
            except Exception as e:
                print(f"Error creating voice channel for {team_name}: {e}")

    summary = f"✓ Channel setup complete!\n\n"
    summary += f"**Text Channels:**\n• Created: {text_created}\n• Updated: {text_updated}\n• Skipped: {text_skipped}\n\n"
    summary += f"**Voice Channels:**\n• Created: {voice_created}\n• Updated: {voice_updated}\n• Skipped: {voice_skipped}"

    await interaction.followup.send(summary)

async def setup_roles(interaction: discord.Interaction, guild: discord.Guild):
    try:
        all_teams = await roles_collection.find({}).to_list(length=100)

        if not all_teams:
            await interaction.followup.send("No teams found in database.")
            return

        roles_created = 0
        roles_existing = 0
        members_assigned = 0
        errors = 0

        for team_data in all_teams:
            team_name = team_data['name']

            role = discord.utils.get(guild.roles, name=team_name)

            if not role:
                try:
                    role = await guild.create_role(
                        name=team_name,
                        color=discord.Color.orange(),
                        mentionable=True,
                        reason="Auto-created by setup command"
                    )
                    roles_created += 1
                    print(f"Created role: {team_name}")
                except Exception as e:
                    print(f"Error creating role {team_name}: {e}")
                    errors += 1
                    continue
            else:
                roles_existing += 1

            team_members = await team_members_collection.find({"team_name": team_name}).to_list(length=100)

            for member_data in team_members:
                discord_member = guild.get_member(int(member_data['discord_id']))

                if discord_member:
                    if role not in discord_member.roles:
                        try:
                            await discord_member.add_roles(role, reason="Assigned by setup command")
                            members_assigned += 1
                            print(f"Assigned {team_name} to {discord_member.name}")
                        except Exception as e:
                            print(f"Error assigning role to {discord_member.name}: {e}")
                            errors += 1
                else:
                    print(f"Member {member_data['discord_id']} not found in guild")

        summary = f"✓ Role assignment complete!\n\n"
        summary += f"**Roles Created:** {roles_created}\n"
        summary += f"**Roles Already Existed:** {roles_existing}\n"
        summary += f"**Members Assigned:** {members_assigned}\n"
        if errors > 0:
            summary += f"**Errors:** {errors}\n"

        await interaction.followup.send(summary)

    except Exception as e:
        print(f'Error in setup_roles: {e}')
        await interaction.followup.send(f"An error occurred: {e}")

@bot.tree.command(name="updateteam", description="Update existing team data", guild=discord.Object(id=serverid))
@app_commands.describe(
    team_name="Team Name",
    github_repo="The GitHub repository associated with the team - optional",
    github_usernames="Comma-separated list of GitHub usernames - optional",
    status="Status of the team - optional"
)
async def updateteam(
    interaction: discord.Interaction,
    team_name: str,
    github_repo: str = None,
    github_usernames: str = None,
    status: str = None
):

    await interaction.response.defer(ephemeral=True)

    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.followup.send("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return

    usernames_list = [username.strip() for username in github_usernames.split(',')] if github_usernames else []

    try:
        existing_role_data = await roles_collection.find_one({"name": team_name})

        if not existing_role_data:
            await interaction.followup.send(f'Team "{team_name}" does not exist. Use `/createteam` to create it first.', ephemeral=True)
            return

        update_fields = {}
        if github_repo is not None:
            update_fields["githubRepo"] = github_repo
        if usernames_list:
            update_fields["githubUsernames"] = usernames_list
        if status is not None:
            update_fields["status"] = status

        if update_fields:
            await roles_collection.update_one({"name": team_name}, {"$set": update_fields})
            await interaction.followup.send(f'Team data for "{team_name}" has been updated.')
        else:
            await interaction.followup.send("No fields to update. Please provide at least one parameter.", ephemeral=True)
    except Exception as error:
        print(f'Error updating team data: {error}')
        await interaction.followup.send("An error occurred while updating team data.")

@bot.tree.command(name="teaminfo", description="View team information", guild=discord.Object(id=serverid))
@app_commands.describe(
    view="What to view: specific team, all teams list, or team members",
    team_name="Team name (required for specific/members view)"
)
@app_commands.choices(view=[
    app_commands.Choice(name="Specific team details", value="specific"),
    app_commands.Choice(name="All teams list", value="all"),
    app_commands.Choice(name="Team members", value="members")
])
async def teaminfo(interaction: discord.Interaction, view: app_commands.Choice[str], team_name: str = None):
    view_value = view.value
    
    if view_value == "all":
        try:
            all_roles = await roles_collection.find({}).to_list(length=100)

            if not all_roles:
                await interaction.response.send_message("No teams found in the database.")
                return

            embed = discord.Embed(
                title="All Teams",
                description=f"Total teams: {len(all_roles)}",
                color=0x3498db,
                timestamp=discord.utils.utcnow()
            )

            for role_data in all_roles:
                status = role_data.get('status', 'No status')
                repo = role_data.get('githubRepo', 'No repo')
                members_count = len(role_data.get('githubUsernames', []))

                embed.add_field(
                    name=role_data['name'],
                    value=f"Status: {status}\nRepo: {repo}\nMembers: {members_count}",
                    inline=True
                )

            await interaction.response.send_message(embed=embed)
        except Exception as error:
            print(f'Error fetching team list: {error}')
            await interaction.response.send_message("An error occurred while fetching the team list.")
    
    elif view_value == "members":
        if not team_name:
            await interaction.response.send_message("Please provide a team name for members view.", ephemeral=True)
            return
        
        try:
            members = await team_members_collection.find({"team_name": team_name}).to_list(length=100)

            if not members:
                await interaction.response.send_message(f'No members found for team "{team_name}".', ephemeral=True)
                return

            embed = discord.Embed(
                title=f"Team: {team_name}",
                description=f"Total members: {len(members)}",
                color=0xff6a00,
                timestamp=discord.utils.utcnow()
            )

            member_list = []
            for mem in members:
                discord_member = interaction.guild.get_member(int(mem['discord_id']))
                if discord_member:
                    member_list.append(f"• {discord_member.mention} ({discord_member.name})")
                else:
                    member_list.append(f"• {mem['discord_username']} (Not in server)")

            embed.add_field(name="Members", value="\n".join(member_list) or "No members", inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            print(f'Error showing team members: {e}')
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    
    else:
        if not team_name:
            await interaction.response.send_message("Please provide a team name for specific view.", ephemeral=True)
            return
        
        try:
            role_data = await roles_collection.find_one({"name": team_name})

            if not role_data:
                await interaction.response.send_message(f'No data found for team "{team_name}".')
                return

            guild = interaction.guild
            role = discord.utils.get(guild.roles, name=team_name)

            if not role:
                await interaction.response.send_message(f'Team "{team_name}" not found in this guild.')
                return

            members_with_role = [member for member in guild.members if role in member.roles]
            member_names = ', '.join([member.name for member in members_with_role]) or 'No members with this role.'

            github_repo_link = f"https://github.com/{role_data['githubRepo']}" if role_data.get('githubRepo') else None

            embed = discord.Embed(
                color=0xff6a00,
                title=f'Team Data for "{team_name}"',
                description=f'Here are the details for team "{team_name}"',
                timestamp=discord.utils.utcnow()
            )

            repo_value = f"[{role_data['githubRepo']}]({github_repo_link})" if github_repo_link else 'Not specified'
            embed.add_field(name='GitHub Repository:', value=repo_value, inline=False)

            if role_data.get('githubUsernames'):
                usernames_links = [f"[{username}](https://github.com/{username})" for username in role_data['githubUsernames']]
                embed.add_field(name='GitHub Usernames:', value=', '.join(usernames_links), inline=False)
            else:
                embed.add_field(name='GitHub Usernames:', value='No usernames available', inline=False)

            embed.add_field(name='Status:', value=role_data.get('status') or 'No status available', inline=False)
            embed.add_field(name='Members with this Role:', value=member_names, inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as error:
            print(f'Error fetching team data: {error}')
            await interaction.response.send_message("An error occurred while fetching team data.")

@bot.tree.command(name="announce", description="Send announcement to all text channels or specific channels", guild=discord.Object(id=serverid))
@app_commands.describe(
    message="The announcement message",
    channels="Optional: Comma-separated channel names (leave empty for all channels)"
)
async def announce(interaction: discord.Interaction, message: str, channels: str = None):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    guild = interaction.guild
    target_channels = []

    if channels:

        channel_names = [ch.strip() for ch in channels.split(',')]
        for ch_name in channel_names:
            channel = discord.utils.get(guild.text_channels, name=ch_name)
            if channel:
                target_channels.append(channel)
            else:
                await interaction.response.send_message(f'Channel "{ch_name}" not found.', ephemeral=True)
                return
    else:

        target_channels = guild.text_channels

    await interaction.response.send_message(f"Sending announcement to {len(target_channels)} channel(s)...", ephemeral=True)

    embed = discord.Embed(
        title="Announcement",
        description=message,
        color=0xff6a00,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Announced by {interaction.user.name}")

    success_count = 0
    for channel in target_channels:
        try:
            await channel.send(embed=embed)
            success_count += 1
        except discord.Forbidden:
            print(f'No permission to send to {channel.name}')
        except Exception as e:
            print(f'Error sending to {channel.name}: {e}')

    await interaction.followup.send(f"✓ Announcement sent to {success_count}/{len(target_channels)} channels!", ephemeral=True)

@bot.tree.command(name="poll", description="Create a poll with multiple options", guild=discord.Object(id=serverid))
@app_commands.describe(
    question="The poll question",
    options="Comma-separated poll options (2-10 options)"
)
async def poll(interaction: discord.Interaction, question: str, options: str):
    option_list = [opt.strip() for opt in options.split(',') if opt.strip()]

    if len(option_list) < 2:
        await interaction.response.send_message("Please provide at least 2 options.", ephemeral=True)
        return

    if len(option_list) > 10:
        await interaction.response.send_message("Maximum 10 options allowed.", ephemeral=True)
        return

    emoji_numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

    embed = discord.Embed(
        title=f"{question}",
        description="React with the corresponding number to vote!",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )

    for i, option in enumerate(option_list):
        embed.add_field(name=f"{emoji_numbers[i]} Option {i+1}", value=option, inline=False)

    embed.set_footer(text=f"Poll created by {interaction.user.name}")

    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    for i in range(len(option_list)):
        await message.add_reaction(emoji_numbers[i])

@bot.tree.command(name="reminder", description="Set a reminder for a deadline", guild=discord.Object(id=serverid))
@app_commands.describe(
    message="Reminder message",
    time_minutes="Time in minutes until reminder"
)
async def reminder(interaction: discord.Interaction, message: str, time_minutes: int):
    if time_minutes < 1:
        await interaction.response.send_message("Time must be at least 1 minute.", ephemeral=True)
        return

    if time_minutes > 10080:  

        await interaction.response.send_message("Maximum reminder time is 7 days (10080 minutes).", ephemeral=True)
        return

    await interaction.response.send_message(f"✓ Reminder set! I'll remind you in {time_minutes} minute(s).", ephemeral=True)

    await asyncio.sleep(time_minutes * 60)

    embed = discord.Embed(
        title="# REMINDER",
        description=message,
        color=0xff0000,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Reminder for {interaction.user.name}")

    try:
        await interaction.channel.send(f"{interaction.user.mention}", embed=embed)
    except Exception as e:
        print(f'Error sending reminder: {e}')

@bot.tree.command(name="manage", description="Manage team members", guild=discord.Object(id=serverid))
@app_commands.describe(
    action="Add or remove a member",
    team_name="Name of the team",
    member="The Discord member"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add member", value="add"),
    app_commands.Choice(name="Remove member", value="remove")
])
async def manage(interaction: discord.Interaction, action: app_commands.Choice[str], team_name: str, member: discord.Member):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return

    action_value = action.value

    try:
        team_exists = await roles_collection.find_one({"name": team_name})
        if not team_exists:
            await interaction.response.send_message(f'Team "{team_name}" does not exist. Create it first with `/createteam`.', ephemeral=True)
            return

        if action_value == "add":
            existing = await team_members_collection.find_one({
                "team_name": team_name,
                "discord_id": str(member.id)
            })

            if existing:
                await interaction.response.send_message(f'{member.mention} is already in team "{team_name}".', ephemeral=True)
                return

            member_data = {
                "team_name": team_name,
                "discord_id": str(member.id),
                "discord_username": member.name,
                "discord_display_name": member.display_name
            }

            await team_members_collection.insert_one(member_data)
            await interaction.response.send_message(f'✓ Added {member.mention} to team "{team_name}" in database. Use `/setup action:roles` to assign Discord roles.', ephemeral=True)
        
        else:
            result = await team_members_collection.delete_one({
                "team_name": team_name,
                "discord_id": str(member.id)
            })

            if result.deleted_count > 0:
                await interaction.response.send_message(f'✓ Removed {member.mention} from team "{team_name}".', ephemeral=True)
            else:
                await interaction.response.send_message(f'{member.mention} is not in team "{team_name}".', ephemeral=True)

    except Exception as e:
        print(f'Error managing team member: {e}')
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="help", description="Show all available commands and their usage", guild=discord.Object(id=serverid))
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Bot Commands Help",
        description="Here are all available commands for the Team Management Bot",
        color=0xff6a00,
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="/createteam",
        value="Create a new team with role and data\n`name` `color` `github_repo` `github_usernames` `status`",
        inline=False
    )
    
    embed.add_field(
        name="/updateteam",
        value="Update existing team information\n`team_name` `github_repo` `github_usernames` `status`",
        inline=False
    )
    
    embed.add_field(
        name="/deleteteam",
        value="Delete a team and all its data\n`team_name`",
        inline=False
    )
    
    embed.add_field(
        name="/setup",
        value="Bulk setup operations - channels, roles, or both\n`action: channels/roles/both`",
        inline=False
    )
    
    embed.add_field(
        name="/teaminfo",
        value="View team information\n`view: specific/all/members` `team_name`",
        inline=False
    )
    
    embed.add_field(
        name="/manage",
        value="Add or remove team members\n`action: add/remove` `team_name` `member`",
        inline=False
    )
    
    embed.add_field(
        name="/announce",
        value="Send announcements to channels\n`message` `channels`",
        inline=False
    )

    embed.add_field(
        name="/githubtimestamp",
        value="Mentions all teams who committed after deadline",
        inline=False
    )
    
    embed.add_field(
        name="/poll",
        value="Create a poll with options\n`question` `options`",
        inline=False
    )
    
    embed.add_field(
        name="/reminder",
        value="Set a timed reminder\n`message` `time_minutes`",
        inline=False
    )
    
    embed.set_footer(text="Admin commands require CT25/CT26 role or Administrator permission")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="deleteteam", description="Delete a team role and all associated data", guild=discord.Object(id=serverid))
@app_commands.describe(
    team_name="Name of the team to delete"
)
async def deleteteam(interaction: discord.Interaction, team_name: str):
    has_permission = await check_permission(interaction)

    if not has_permission:
        await interaction.response.send_message("You do not have permission to use this command. Only CT25/CT26 admins can use this.", ephemeral=True)
        return
        
    team_exists = await roles_collection.find_one({"name": team_name})
    if not team_exists:
            await interaction.response.send_message(f'Team "{team_name}" does not exist. Create it first with `/createteam`.', ephemeral=True)
            return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    try:
        await roles_collection.delete_one({"name": team_name})
        await team_members_collection.delete_many({"team_name": team_name})
        
        role = discord.utils.get(guild.roles, name=team_name)
        if role:
            await role.delete(reason=f"Team deleted by {interaction.user.name}")
        channels = discord.utils.get(guild.channels, name=team_name)
        if channels:
            await channels.delete(reason=f"Team deleted by {interaction.user.name}")

        await interaction.followup.send(f'✓ Deleted team "{team_name}" and all associated data.')


    except Exception as e:
        print(f'Error deleting team: {e}')
        await interaction.followup.send(f"An error occurred: {e}")

if __name__ == '__main__':
    bot.run(token)


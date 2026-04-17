import os
import json
from datetime import datetime

import discord
from discord.ext import commands

# =========================
# CONFIG
# =========================
GUILD_ID = 1487280640658505838
CANAL_CONFIG_ID = 1493027270070243439
CANAL_CONVITES_ID = 1493077864441057420
CARGO_AUTO_ID = 1492955610117837021
CARGO_GERENTE_ID = 1492955199831281824
CANAL_BAN_ID = 1494178007995121674
CARGO_STAFF_ID = 1494179375254343740

BLACKLIST_FILE = "blacklist.json"
BANLOG_FILE = "banlog.json"
PAINEL_MARKER = "PAINEL_CARGOS_CONFIG_V1"
CARGOS_BLOQUEADOS = set()

# Coloque o token em variável de ambiente chamada DISCORD_BOT_TOKEN


# =========================
# INTENTS
# =========================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.panel_message = None
bot.panel_view = None
bot.panel_ready_once = False


# =========================
# AUXILIARES
# =========================
def carregar_json(path: str) -> dict:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def salvar_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)



def usuario_na_blacklist(user_id: int):
    data = carregar_json(BLACKLIST_FILE)
    return data.get(str(user_id))



def usuario_e_gerente(member: discord.Member) -> bool:
    return any(role.id == CARGO_GERENTE_ID for role in member.roles)



def staff_ou_gerente(member: discord.Member) -> bool:
    cargos = [role.id for role in member.roles]
    return CARGO_STAFF_ID in cargos or CARGO_GERENTE_ID in cargos



def cargos_disponiveis(guild: discord.Guild, bot_member: discord.Member) -> list[discord.Role]:
    cargos = []

    print(f"Cargo mais alto do bot: {bot_member.top_role.name} ({bot_member.top_role.position})")

    for role in guild.roles:
        print(f"Analisando cargo: {role.name} | pos={role.position} | managed={role.managed} | id={role.id}")

        if role.is_default():
            print("  -> ignorado: @everyone")
            continue

        if role.managed:
            print("  -> ignorado: managed")
            continue

        if role.id in CARGOS_BLOQUEADOS:
            print("  -> ignorado: bloqueado")
            continue

        if role >= bot_member.top_role:
            print("  -> ignorado: acima ou igual ao cargo do bot")
            continue

        print("  -> adicionado na lista")
        cargos.append(role)

    cargos.sort(key=lambda r: r.position, reverse=True)
    print(f"Total de cargos disponíveis: {len(cargos)}")
    return cargos


async def buscar_painel_existente(canal: discord.TextChannel) -> discord.Message | None:
    async for msg in canal.history(limit=100):
        if msg.author.id != bot.user.id:
            continue

        if not msg.embeds:
            continue

        embed = msg.embeds[0]
        footer_text = embed.footer.text if embed.footer else ""
        desc = embed.description or ""

        if PAINEL_MARKER in footer_text or PAINEL_MARKER in desc:
            return msg

    return None


# =========================
# MODAIS
# =========================
class UserIdModal(discord.ui.Modal, title="Informar ID do usuário"):
    user_id = discord.ui.TextInput(
        label="ID do usuário",
        placeholder="Cole aqui o ID da pessoa",
        required=True,
        min_length=17,
        max_length=25
    )

    def __init__(self, panel_view: "RolePanelView"):
        super().__init__()
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use isso dentro do servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        try:
            target_id = int(self.user_id.value.strip())
        except ValueError:
            await interaction.response.send_message("ID inválido.", ephemeral=True)
            return

        self.panel_view.selected_user_id = target_id
        await interaction.response.defer(ephemeral=True)
        await self.panel_view.update_panel_message()
        await interaction.followup.send(f"ID definido como `{target_id}`.", ephemeral=True)


class ChangeNicknameModal(discord.ui.Modal, title="Alterar apelido no servidor"):
    new_nick = discord.ui.TextInput(
        label="Novo apelido",
        placeholder="Digite o novo apelido no servidor",
        required=True,
        max_length=32
    )

    def __init__(self, panel_view: "RolePanelView"):
        super().__init__()
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use isso dentro do servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este botão.", ephemeral=True)
            return

        if self.panel_view.selected_user_id is None:
            await interaction.response.send_message("Informe o ID do usuário primeiro no painel.", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(self.panel_view.selected_user_id)

        if member is None:
            try:
                member = await guild.fetch_member(self.panel_view.selected_user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None

        if member is None:
            await interaction.response.send_message("Não encontrei esse membro no servidor.", ephemeral=True)
            return

        bot_member = guild.me or guild.get_member(interaction.client.user.id)
        if bot_member is None:
            await interaction.response.send_message("Não consegui validar o bot no servidor.", ephemeral=True)
            return

        if member.top_role >= bot_member.top_role:
            await interaction.response.send_message(
                "Não posso alterar o apelido dessa pessoa porque o cargo dela está acima ou no mesmo nível do bot.",
                ephemeral=True
            )
            return

        novo_apelido = self.new_nick.value.strip()

        try:
            await member.edit(nick=novo_apelido, reason=f"Apelido alterado por {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para alterar o apelido dessa pessoa.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Erro ao alterar o apelido: {e}", ephemeral=True)
            return

        canal_convites = guild.get_channel(CANAL_CONVITES_ID)
        if isinstance(canal_convites, discord.TextChannel):
            embed_log = discord.Embed(title="Apelido alterado manualmente", color=discord.Color.orange())
            embed_log.add_field(name="Membro", value=f"{member.mention} (`{member.id}`)", inline=False)
            embed_log.add_field(name="Novo apelido", value=novo_apelido, inline=False)
            embed_log.add_field(name="Alterado por", value=interaction.user.mention, inline=False)
            embed_log.set_thumbnail(url=member.display_avatar.url)
            try:
                await canal_convites.send(embed=embed_log)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            f"Apelido de {member.mention} alterado para **{novo_apelido}**.",
            ephemeral=True
        )


# =========================
# VIEW DO PAINEL
# =========================
class RolePanelView(discord.ui.View):
    def __init__(self, guild: discord.Guild, cargos: list[discord.Role]):
        super().__init__(timeout=None)
        self.guild_id = guild.id
        self.cargos = cargos
        self.page = 0

        self.selected_role_id: int | None = None
        self.selected_user_id: int | None = None
        self.message: discord.Message | None = None

        self.select_menu = discord.ui.Select(
            placeholder="Selecione um cargo...",
            min_values=1,
            max_values=1,
            options=[],
            custom_id="painel_cargos_select"
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

        self.prev_button = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="painel_cargos_prev"
        )
        self.prev_button.callback = self.prev_callback
        self.add_item(self.prev_button)

        self.next_button = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="painel_cargos_next"
        )
        self.next_button.callback = self.next_callback
        self.add_item(self.next_button)

        self.id_button = discord.ui.Button(
            label="Informar ID",
            style=discord.ButtonStyle.primary,
            custom_id="painel_cargos_id"
        )
        self.id_button.callback = self.id_button_callback
        self.add_item(self.id_button)

        self.nick_button = discord.ui.Button(
            label="Alterar apelido",
            style=discord.ButtonStyle.primary,
            custom_id="painel_cargos_nick"
        )
        self.nick_button.callback = self.nick_button_callback
        self.add_item(self.nick_button)

        self.confirm_button = discord.ui.Button(
            label="Confirmar",
            style=discord.ButtonStyle.success,
            custom_id="painel_cargos_confirm"
        )
        self.confirm_button.callback = self.confirm_callback
        self.add_item(self.confirm_button)

        self.refresh_options()

    def refresh_options(self):
        start = self.page * 25
        end = start + 25
        chunk = self.cargos[start:end]

        options = []
        for role in chunk:
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"ID: {role.id}"[:100],
                    default=(self.selected_role_id == role.id)
                )
            )

        if not options:
            options = [
                discord.SelectOption(
                    label="Nenhum cargo disponível",
                    value="0",
                    description="Sem cargos para mostrar"
                )
            ]
            self.select_menu.disabled = True
            self.confirm_button.disabled = True
        else:
            self.select_menu.disabled = False
            self.confirm_button.disabled = False

        self.select_menu.options = options
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = (self.page + 1) * 25 >= len(self.cargos)

    def make_embed(self, guild: discord.Guild) -> discord.Embed:
        total_pages = max(1, (len(self.cargos) + 24) // 25)

        role_text = "Nenhum cargo selecionado"
        if self.selected_role_id:
            role = guild.get_role(self.selected_role_id)
            if role:
                role_text = f"{role.mention} (`{role.id}`)"
            else:
                role_text = f"`{self.selected_role_id}`"

        user_text = "Nenhum ID informado"
        if self.selected_user_id:
            member = guild.get_member(self.selected_user_id)
            if member:
                user_text = f"{member.mention} (`{member.id}`)"
            else:
                user_text = f"`{self.selected_user_id}`"

        embed = discord.Embed(
            title="Painel de adicionar cargos",
            description="Selecione um cargo no menu, informe o ID da pessoa e clique em **Confirmar**.",
            color=discord.Color.gold()
        )
        embed.add_field(name="ID do usuário", value=user_text, inline=False)
        embed.add_field(name="Cargo selecionado", value=role_text, inline=False)
        embed.add_field(name="Página", value=f"{self.page + 1}/{total_pages}", inline=True)
        embed.add_field(
            name="Cargos disponíveis",
            value=str(len(self.cargos)) if self.cargos else "Nenhum cargo disponível",
            inline=True
        )
        embed.set_footer(text=f"Painel automático do bot | {PAINEL_MARKER}")
        return embed

    async def update_panel_message(self):
        if not self.message:
            return

        guild = self.message.guild
        if guild is None:
            return

        bot_member = guild.me or guild.get_member(bot.user.id)
        if bot_member is not None:
            self.cargos = cargos_disponiveis(guild, bot_member)

        max_page = max(0, (len(self.cargos) - 1) // 25) if self.cargos else 0
        if self.page > max_page:
            self.page = max_page

        self.refresh_options()
        await self.message.edit(embed=self.make_embed(guild), view=self)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        values = interaction.data.get("values", []) if interaction.data else []
        value = values[0] if values else "0"

        if value != "0":
            self.selected_role_id = int(value)

        self.refresh_options()
        await interaction.response.edit_message(embed=self.make_embed(interaction.guild), view=self)

    async def prev_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        if self.page > 0:
            self.page -= 1

        self.refresh_options()
        await interaction.response.edit_message(embed=self.make_embed(interaction.guild), view=self)

    async def next_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        if (self.page + 1) * 25 < len(self.cargos):
            self.page += 1

        self.refresh_options()
        await interaction.response.edit_message(embed=self.make_embed(interaction.guild), view=self)

    async def id_button_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        await interaction.response.send_modal(UserIdModal(self))

    async def nick_button_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        if self.selected_user_id is None:
            await interaction.response.send_message("Informe o ID do usuário primeiro.", ephemeral=True)
            return

        await interaction.response.send_modal(ChangeNicknameModal(self))

    async def confirm_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse painel só funciona no servidor.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not usuario_e_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este painel.", ephemeral=True)
            return

        if self.selected_user_id is None:
            await interaction.response.send_message("Informe o ID do usuário primeiro.", ephemeral=True)
            return

        if self.selected_role_id is None:
            await interaction.response.send_message("Selecione um cargo primeiro.", ephemeral=True)
            return

        guild = interaction.guild
        role = guild.get_role(self.selected_role_id)
        if role is None:
            await interaction.response.send_message("Cargo não encontrado.", ephemeral=True)
            return

        member = guild.get_member(self.selected_user_id)
        if member is None:
            try:
                member = await guild.fetch_member(self.selected_user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None

        if member is None:
            await interaction.response.send_message("Não encontrei esse membro no servidor.", ephemeral=True)
            return

        bot_member = guild.me or guild.get_member(bot.user.id)
        if bot_member is None:
            await interaction.response.send_message("Não consegui validar o bot no servidor.", ephemeral=True)
            return

        if role >= bot_member.top_role:
            await interaction.response.send_message(
                "Não posso adicionar esse cargo porque ele está acima ou no mesmo nível do cargo do bot.",
                ephemeral=True
            )
            return

        if role in member.roles:
            await interaction.response.send_message(f"{member.mention} já possui o cargo {role.mention}.", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason=f"Cargo adicionado pelo painel por {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para adicionar esse cargo.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Erro ao adicionar cargo: {e}", ephemeral=True)
            return

        canal_convites = guild.get_channel(CANAL_CONVITES_ID)
        if isinstance(canal_convites, discord.TextChannel):
            embed_log = discord.Embed(title="Cargo adicionado manualmente", color=discord.Color.blurple())
            embed_log.add_field(name="Membro", value=f"{member.mention} (`{member.id}`)", inline=False)
            embed_log.add_field(name="Cargo", value=role.mention, inline=False)
            embed_log.add_field(name="Adicionado por", value=interaction.user.mention, inline=False)
            embed_log.set_thumbnail(url=member.display_avatar.url)
            try:
                await canal_convites.send(embed=embed_log)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(f"Cargo {role.mention} adicionado em {member.mention}.", ephemeral=True)


# =========================
# VIEW DE BANIMENTO
# =========================
class BanActionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Remover Banimento", style=discord.ButtonStyle.success, custom_id="remover_banimento")
    async def remover_banimento(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use isso dentro do servidor.", ephemeral=True)
            return

        if not staff_ou_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para isso.", ephemeral=True)
            return

        try:
            user = await bot.fetch_user(self.user_id)
            await interaction.guild.unban(user, reason=f"Desbanido por {interaction.user}")
        except discord.NotFound:
            await interaction.response.send_message("Esse usuário não está banido.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para remover o banimento.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Erro ao remover banimento: {e}", ephemeral=True)
            return

        await interaction.response.send_message(f"Banimento removido do usuário `{self.user_id}`.", ephemeral=True)

    @discord.ui.button(label="Adicionar à blacklist", style=discord.ButtonStyle.secondary, custom_id="adicionar_blacklist")
    async def adicionar_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use isso dentro do servidor.", ephemeral=True)
            return

        if not staff_ou_gerente(interaction.user):
            await interaction.response.send_message("Você não tem permissão para isso.", ephemeral=True)
            return

        data = carregar_json(BLACKLIST_FILE)
        uid = str(self.user_id)

        if uid in data:
            await interaction.response.send_message("Esse usuário já está na blacklist.", ephemeral=True)
            return

        data[uid] = {
            "motivo": "Adicionado pelo botão do sistema de banimento",
            "adicionado_por": str(interaction.user.id),
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
        salvar_json(BLACKLIST_FILE, data)

        await interaction.response.send_message(f"Usuário `{self.user_id}` adicionado à blacklist.", ephemeral=True)


# =========================
# COMANDOS
# =========================
@bot.command(name="ban")
async def ban_command(ctx, user_id: int, *, motivo: str = "Motivo não informado"):
    if not isinstance(ctx.author, discord.Member):
        return

    if not staff_ou_gerente(ctx.author):
        await ctx.send("❌ Você não tem permissão para usar esse comando.")
        return

    guild = ctx.guild
    if guild is None:
        return

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send("❌ Usuário não encontrado.")
        return
    except discord.HTTPException:
        await ctx.send("❌ Erro ao buscar usuário.")
        return

    try:
        await guild.ban(user, reason=f"Punido por {ctx.author} - Motivo: {motivo}", delete_message_seconds=0)
    except discord.Forbidden:
        await ctx.send("❌ Não tenho permissão para banir esse usuário.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"❌ Erro ao banir usuário: {e}")
        return

    banlog = carregar_json(BANLOG_FILE)
    banlog[str(user_id)] = {
        "motivo": motivo,
        "moderador": str(ctx.author.id),
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
    salvar_json(BANLOG_FILE, banlog)

    canal_ban = guild.get_channel(CANAL_BAN_ID)
    if isinstance(canal_ban, discord.TextChannel):
        embed = discord.Embed(title="🚫 | Banido", color=discord.Color.red())
        embed.add_field(name="👤 Membro", value=f"<@{user_id}>", inline=False)
        embed.add_field(name="ID", value=str(user_id), inline=False)
        embed.add_field(name="🛡️ Moderador", value=ctx.author.mention, inline=False)
        embed.add_field(name="ID do moderador", value=str(ctx.author.id), inline=False)
        embed.add_field(name="📄 Motivo", value=f"Punido por {ctx.author} — Motivo: {motivo}", inline=False)
        embed.set_footer(text=datetime.now().strftime("%d/%m/%Y às %H:%M"))
        await canal_ban.send(embed=embed, view=BanActionView(user_id))

    await ctx.send(f"✅ Usuário `{user_id}` foi banido com sucesso.")


@bot.command(name="unban")
async def unban_command(ctx, user_id: int):
    if not isinstance(ctx.author, discord.Member):
        return

    if not staff_ou_gerente(ctx.author):
        await ctx.send("❌ Você não tem permissão para usar esse comando.")
        return

    guild = ctx.guild
    if guild is None:
        return

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send("❌ Usuário não encontrado.")
        return
    except discord.HTTPException:
        await ctx.send("❌ Erro ao buscar usuário.")
        return

    try:
        await guild.unban(user, reason=f"Desbanido por {ctx.author}")
    except discord.NotFound:
        await ctx.send("⚠️ Esse usuário não está banido.")
        return
    except discord.Forbidden:
        await ctx.send("❌ Não tenho permissão para desbanir esse usuário.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"❌ Erro ao desbanir usuário: {e}")
        return

    await ctx.send(f"✅ Usuário `{user_id}` foi desbanido com sucesso.")


@bot.command(name="blacklist")
async def blacklist_command(ctx, user_id: int, *, motivo: str = "Motivo não informado"):
    if not isinstance(ctx.author, discord.Member):
        return

    if not staff_ou_gerente(ctx.author):
        await ctx.send("❌ Você não tem permissão para usar esse comando.")
        return

    data = carregar_json(BLACKLIST_FILE)
    uid = str(user_id)

    if uid in data:
        await ctx.send("⚠️ Esse usuário já está na blacklist.")
        return

    data[uid] = {
        "motivo": motivo,
        "adicionado_por": str(ctx.author.id),
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
    salvar_json(BLACKLIST_FILE, data)

    await ctx.send(f"✅ Usuário `{user_id}` adicionado à blacklist.")


@bot.command(name="unblacklist")
async def unblacklist_command(ctx, user_id: int):
    if not isinstance(ctx.author, discord.Member):
        return

    if not staff_ou_gerente(ctx.author):
        await ctx.send("❌ Você não tem permissão para usar esse comando.")
        return

    data = carregar_json(BLACKLIST_FILE)
    uid = str(user_id)

    if uid not in data:
        await ctx.send("⚠️ Esse usuário não está na blacklist.")
        return

    del data[uid]
    salvar_json(BLACKLIST_FILE, data)

    await ctx.send(f"✅ Usuário `{user_id}` removido da blacklist.")


@bot.command(name="bl")
async def check_blacklist(ctx, user_id: int):
    if not isinstance(ctx.author, discord.Member):
        return

    data = carregar_json(BLACKLIST_FILE)
    uid = str(user_id)

    embed = discord.Embed()

    if uid in data:
        info = data[uid]
        embed.title = "⚠️ Usuário na BLACKLIST"
        embed.color = discord.Color.red()
        embed.add_field(name="Usuário", value=f"<@{user_id}>", inline=False)
        embed.add_field(name="ID", value=str(user_id), inline=False)
        embed.add_field(name="Motivo", value=info.get("motivo", "Não informado"), inline=False)
        embed.add_field(name="Adicionado por", value=f"<@{info.get('adicionado_por')}>", inline=False)
        embed.add_field(name="Data", value=info.get("data", "Desconhecida"), inline=False)
    else:
        embed.title = "✅ Usuário LIMPO"
        embed.color = discord.Color.green()
        embed.description = f"O usuário <@{user_id}> (`{user_id}`) não está na blacklist."

    await ctx.send(embed=embed)


# =========================
# PAINEL
# =========================
async def setup_or_update_config_panel():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Guild não encontrada.")
        return

    canal_config = guild.get_channel(CANAL_CONFIG_ID)
    if not isinstance(canal_config, discord.TextChannel):
        print("Canal config não encontrado.")
        return

    bot_member = guild.me or guild.get_member(bot.user.id)
    if bot_member is None:
        print("Bot não encontrado na guild.")
        return

    cargos = cargos_disponiveis(guild, bot_member)
    view = RolePanelView(guild, cargos)
    bot.add_view(view)

    painel_antigo = await buscar_painel_existente(canal_config)

    if painel_antigo:
        try:
            await painel_antigo.edit(embed=view.make_embed(guild), view=view)
            view.message = painel_antigo
            bot.panel_message = painel_antigo
            bot.panel_view = view
            print("Painel antigo encontrado e atualizado.")
            return
        except discord.HTTPException:
            print("Falha ao editar painel antigo. Criando novo.")

    nova_msg = await canal_config.send(embed=view.make_embed(guild), view=view)
    view.message = nova_msg
    bot.panel_message = nova_msg
    bot.panel_view = view
    print("Novo painel criado no canal config.")


# =========================
# EVENTOS
# =========================
@bot.event
async def on_member_join(member: discord.Member):
    cargo = member.guild.get_role(CARGO_AUTO_ID)
    canal_convites = member.guild.get_channel(CANAL_CONVITES_ID)

    if cargo is None:
        print("Cargo automático não encontrado.")
        return

    try:
        await member.add_roles(cargo, reason="Cargo automático ao entrar no servidor")
    except discord.Forbidden:
        print("Sem permissão para adicionar o cargo automático.")
        return
    except discord.HTTPException as e:
        print(f"Erro ao adicionar cargo automático: {e}")
        return

    if isinstance(canal_convites, discord.TextChannel):
        embed = discord.Embed(title="Cargo automático aplicado", color=discord.Color.green())
        embed.add_field(name="Membro", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Cargo recebido", value=cargo.mention, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await canal_convites.send(embed=embed)
        except discord.HTTPException:
            pass


@bot.event
async def on_ready():
    print(f"🔥 Bot online como {bot.user}")

    if not bot.panel_ready_once:
        bot.panel_ready_once = True
        try:
            await setup_or_update_config_panel()
        except Exception as e:
            print("Erro ao montar o painel de cargos:")
            print(e)


 
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Defina a variável de ambiente DISCORD_BOT_TOKEN com o token do bot.")

bot.run(TOKEN)
import logging
import os
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ------------------------------------------------------------------
# Configuração
# ------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")
SUPORTE_USERNAME = "@seu_suporte"  # troque pelo contato de suporte real

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Estado simples em memória para saber quando um usuário está
# digitando um valor para adicionar saldo (poderia virar uma
# ConversationHandler se o fluxo crescer)
AGUARDANDO_VALOR = set()


# ------------------------------------------------------------------
# Banco de dados
# ------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            nome        TEXT,
            saldo       REAL DEFAULT 0,
            criado_em   TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_or_create_usuario(user_id: int, username: str, nome: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO usuarios (user_id, username, nome, saldo, criado_em) "
            "VALUES (?, ?, ?, 0, ?)",
            (user_id, username, nome, datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM usuarios WHERE user_id = ?", (user_id,)
        ).fetchone()
    conn.close()
    return row


def adicionar_saldo(user_id: int, valor: float):
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET saldo = saldo + ? WHERE user_id = ?",
        (valor, user_id),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Teclado / Menu
# ------------------------------------------------------------------
def menu_principal():
    keyboard = [
        [InlineKeyboardButton("🛒 Comprar", callback_data="comprar")],
        [InlineKeyboardButton("👤 Perfil", callback_data="perfil")],
        [InlineKeyboardButton("💰 Adicionar saldo", callback_data="add_saldo")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="suporte")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_usuario(user.id, user.username or "", user.first_name or "")

    texto = (
        f"👋 Olá, {user.first_name}! Seja bem-vindo(a)!\n\n"
        "Escolha uma opção abaixo para continuar:"
    )
    await update.message.reply_text(texto, reply_markup=menu_principal())


async def botao_clicado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    dados = get_or_create_usuario(user.id, user.username or "", user.first_name or "")

    if query.data == "comprar":
        # TODO: listar produtos reais aqui
        texto = (
            "🛒 *Comprar*\n\n"
            "Ainda não há produtos cadastrados.\n"
            "Em breve você poderá escolher entre as opções disponíveis."
        )
        await query.edit_message_text(texto, reply_markup=menu_principal(), parse_mode="Markdown")

    elif query.data == "perfil":
        texto = (
            "👤 *Seu Perfil*\n\n"
            f"ID: `{dados['user_id']}`\n"
            f"Nome: {dados['nome']}\n"
            f"Usuário: @{dados['username'] if dados['username'] else 'não definido'}\n"
            f"Saldo: R$ {dados['saldo']:.2f}"
        )
        await query.edit_message_text(texto, reply_markup=menu_principal(), parse_mode="Markdown")

    elif query.data == "add_saldo":
        AGUARDANDO_VALOR.add(user.id)
        texto = (
            "💰 *Adicionar saldo*\n\n"
            "Digite o valor que deseja adicionar (ex: 20 ou 20.50):"
        )
        await query.edit_message_text(texto, parse_mode="Markdown")

    elif query.data == "suporte":
        texto = (
            "🆘 *Suporte*\n\n"
            f"Precisa de ajuda? Fale com a gente: {SUPORTE_USERNAME}"
        )
        await query.edit_message_text(texto, reply_markup=menu_principal(), parse_mode="Markdown")


async def receber_valor_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in AGUARDANDO_VALOR:
        return  # ignora mensagens fora do fluxo de adicionar saldo

    texto_usuario = update.message.text.strip().replace(",", ".")
    try:
        valor = float(texto_usuario)
        if valor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Digite apenas um número, ex: 20 ou 20.50"
        )
        return

    # TODO: aqui entraria a integração real de pagamento (Pix, cartão, etc.)
    # Por enquanto o saldo é adicionado diretamente para fins de teste.
    adicionar_saldo(user.id, valor)
    AGUARDANDO_VALOR.discard(user.id)

    await update.message.reply_text(
        f"✅ Saldo de R$ {valor:.2f} adicionado com sucesso!",
        reply_markup=menu_principal(),
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Menu:", reply_markup=menu_principal())


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(botao_clicado))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_saldo))

    logger.info("Bot iniciado. Pressione Ctrl+C para parar.")
    app.run_polling()


if __name__ == "__main__":
    main()


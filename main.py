import json
import logging
import os
from threading import Thread
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

import config

# Logging
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

HISTORY = 'compras.json'
if not os.path.isfile(HISTORY):
    with open(HISTORY, 'w') as f:
        json.dump([], f, indent=2)

app = Flask(__name__)

CHOOSING, SELECT_PLAN, SELECT_PAYMENT, WAIT_PROOF = range(4)

PLANS = {
    "1 mes – 11 USD": ("1 mes", 11),
    "3 meses – 15 USD": ("3 meses", 15),
    "1 año – 27 USD": ("1 año", 27),
}
PAY_METHODS = ["PayPal", "Zelle", "CUP", "Saldo móvil"]

def save_purchase(entry):
    with open(HISTORY, 'r+') as f:
        data = json.load(f)
        data.append(entry)
        f.seek(0)
        json.dump(data, f, indent=2)

# — /start
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [["1 mes – 11 USD", "3 meses – 15 USD"], ["1 año – 27 USD", "/miestado"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "👋 ¡Bienvenido! Elige un plan o /miestado para tu historial.",
        reply_markup=markup
    )
    return SELECT_PLAN

# — /help
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start para comprar\n"
        "/miestado para tu historial\n"
        "/cancelar para cancelar en cualquier paso"
    )

# — /miestado
async def miestado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with open(HISTORY) as f:
        data = json.load(f)
    yours = [e for e in data if e.get('payer_id')==user.id]
    if not yours:
        await update.message.reply_text("📭 No tienes compras.")
    else:
        lines = [f"{e['plan']} — {e['price']} USD — {e['status']}" for e in yours]
        await update.message.reply_text("📑 Tu historial:\n" + "\n".join(lines))

# — Plan seleccionado
async def plan_sel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text not in PLANS and text != "/miestado":
        await update.message.reply_text("⚠️ Plan no válido, /start para volver.")
        return ConversationHandler.END
    if text == "/miestado":
        return await miestado(update, ctx)
    plan, price = PLANS[text]
    ctx.user_data['plan'] = plan
    ctx.user_data['price'] = price
    kb = [[m] for m in PAY_METHODS] + [["🚫 Cancelar"]]
    await update.message.reply_text(
        f"✅ {plan} — {price} USD\nElige método:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return SELECT_PAYMENT

# — Método de pago
async def payment_sel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🚫 Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if text not in PAY_METHODS:
        await update.message.reply_text("⚠️ Método no válido.")
        return SELECT_PAYMENT

    method = text
    plan = ctx.user_data['plan']
    price = ctx.user_data['price']
    ctx.user_data['method'] = method

    if method == "PayPal":
        user_id = update.effective_user.id
        link = (
            f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick"
            f"&business={config.PAYPAL_BUSINESS}"
            f"&item_name={plan}"
            f"&amount={price}"
            f"&currency_code=USD"
            f"&no_shipping=1"
            f"&custom={user_id}"
            f"&return={config.PAYPAL_RETURN_URL}"
            f"&cancel_return={config.PAYPAL_CANCEL_URL}"
        )
        await update.message.reply_text(
            f"💳 Paga con PayPal:\n{link}\n\n"
            "Esperando confirmación de PayPal..."
        )
        # NOTA: El IPN se encargará de notificar éxito o fallo
        return ConversationHandler.END

    # Otros métodos: pedir comprobante
    await update.message.reply_text(
        f"📤 Envía tu comprobante de {method}.",
        reply_markup=ReplyKeyboardMarkup([["🚫 Cancelar"]], resize_keyboard=True)
    )
    return WAIT_PROOF

# — Recibo de comprobante
async def proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="🚫 Cancelar":
        await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if update.message.photo or update.message.document:
        user = update.effective_user
        entry = {
            'plan': ctx.user_data['plan'],
            'price': ctx.user_data['price'],
            'method': ctx.user_data['method'],
            'payer_id': user.id,
            'payer_username': user.username,
            'status': 'proof_sent'
        }
        save_purchase(entry)
        # notificar admin
        for a in config.ADMINS:
            await ctx.bot.send_message(a,
                f"🛎️ Nueva prueba:\n"
                f"{entry['plan']} — {entry['price']} USD — {entry['method']}\n"
                f"@{entry['payer_username']}"
            )
        await update.message.reply_text("✅ Comprobante recibido.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text("⚠️ Envía foto o doc.")
    return WAIT_PROOF

# — cancelar
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# — IPN PayPal
@app.route("/paypal-ipn", methods=["POST"])
def paypal_ipn():
    data = request.form.to_dict()
    # guardar
    entry = {
        'plan': data.get('item_name'),
        'price': data.get('mc_gross'),
        'payer_id': int(data.get('custom',0)),
        'status': 'completed'
    }
    save_purchase(entry)
    bot = ctx = ApplicationBuilder().token(config.TOKEN).build()
    user_id = entry['payer_id']
    # notificar user
    bot.bot.send_message(user_id, f"✅ Tu pago de {entry['plan']} fue exitoso.")
    # notificar admins
    for a in config.ADMINS:
        bot.bot.send_message(a,
            f"🛍️ Pago confirmado:\n"
            f"{entry['plan']} — {entry['price']} USD\n"
            f"UserID: {user_id}"
        )
    return '',200

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__=="__main__":
    Thread(target=run_flask).start()
    app_bot = ApplicationBuilder().token(config.TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_sel)],
            SELECT_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_sel)],
            WAIT_PROOF:   [MessageHandler((filters.PHOTO|filters.Document.ALL)|filters.Regex("^🚫 Cancelar$"), proof)],
        },
        fallbacks=[CommandHandler("cancelar", cancel)],
        per_message=False
    )
    app_bot.add_handler(conv)
    app_bot.add_handler(CommandHandler("help", help_cmd))
    app_bot.add_handler(CommandHandler("miestado", miestado))
    app_bot.run_polling()

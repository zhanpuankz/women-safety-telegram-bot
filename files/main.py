import asyncio
import json
import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8863993802:AAHEahtRJQQDjAdc-P2VgSF3E1f6jf_VZGc")
CONTACTS_FILE = "trusted_contacts.json"

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ── FSM States ──────────────────────────────────────────────────────────────

class SOSState(StatesGroup):
    waiting_for_location = State()

class ContactState(StatesGroup):
    waiting_for_contact = State()


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_contacts() -> dict:
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_contacts(contacts: dict):
    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f, indent=2)

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 SOS"), KeyboardButton(text="📍 Share Location")],
            [KeyboardButton(text="👤 Trusted Contact"), KeyboardButton(text="🚪 Safe Exit")],
        ],
        resize_keyboard=True,
        persistent=True
    )


# ── /start ───────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Welcome to *SafeGuard Bot*\n\n"
        "This bot helps you stay safe. Here's what you can do:\n\n"
        "🆘 *SOS* — Send an emergency alert with your location\n"
        "📍 *Share Location* — Share your location with trusted contact\n"
        "👤 *Trusted Contact* — Add a person to notify in emergencies\n"
        "🚪 *Safe Exit* — Quickly close the app without a trace\n\n"
        "Use the buttons below to get started.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


# ── SOS ──────────────────────────────────────────────────────────────────────

@dp.message(F.text == "🆘 SOS")
async def sos_handler(message: Message, state: FSMContext):
    await state.set_state(SOSState.waiting_for_location)
    await message.answer(
        "🆘 *SOS activated!*\n\nPlease send your location so we can alert your trusted contact.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Send my location", request_location=True)],
                      [KeyboardButton(text="❌ Cancel")]],
            resize_keyboard=True
        )
    )

@dp.message(SOSState.waiting_for_location, F.location)
async def sos_location_received(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = str(message.from_user.id)

    emergency_text = (
        f"🆘 *EMERGENCY ALERT*\n\n"
        f"I need help. My location is:\n"
        f"📍 Latitude: `{lat}`\n"
        f"📍 Longitude: `{lon}`\n\n"
        f"https://maps.google.com/?q={lat},{lon}"
    )

    await message.answer(emergency_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    contacts = load_contacts()
    if user_id in contacts:
        contact_id = contacts[user_id].get("telegram_id")
        contact_name = contacts[user_id].get("name", "Unknown")
        if contact_id:
            try:
                await bot.send_message(contact_id, emergency_text, parse_mode="Markdown")
                await message.answer(f"✅ Alert sent to *{contact_name}*.", parse_mode="Markdown")
            except Exception:
                await message.answer("⚠️ Could not reach your trusted contact. Make sure they have started the bot.")
    else:
        await message.answer(
            "⚠️ You have no trusted contact set. Please add one using the *👤 Trusted Contact* button.",
            parse_mode="Markdown"
        )

    await state.clear()

@dp.message(SOSState.waiting_for_location, F.text == "❌ Cancel")
async def sos_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("SOS cancelled.", reply_markup=get_main_keyboard())


# ── Share Location ────────────────────────────────────────────────────────────

@dp.message(F.text == "📍 Share Location")
async def share_location_handler(message: Message):
    user_id = str(message.from_user.id)
    contacts = load_contacts()

    if user_id not in contacts:
        await message.answer(
            "⚠️ No trusted contact found. Please add one using *👤 Trusted Contact* first.",
            parse_mode="Markdown"
        )
        return

    await message.answer(
        "📍 Send your current location and it will be forwarded to your trusted contact.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Send my location", request_location=True)],
                      [KeyboardButton(text="❌ Cancel")]],
            resize_keyboard=True
        )
    )

@dp.message(F.location)
async def location_received(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == SOSState.waiting_for_location:
        return  # handled above

    lat = message.location.latitude
    lon = message.location.longitude
    user_id = str(message.from_user.id)

    contacts = load_contacts()
    if user_id in contacts:
        contact_id = contacts[user_id].get("telegram_id")
        contact_name = contacts[user_id].get("name", "Someone")
        if contact_id:
            try:
                await bot.send_message(
                    contact_id,
                    f"📍 *Location shared by a contact:*\n"
                    f"Latitude: `{lat}`, Longitude: `{lon}`\n"
                    f"https://maps.google.com/?q={lat},{lon}",
                    parse_mode="Markdown"
                )
                await message.answer(f"✅ Location sent to *{contact_name}*.", parse_mode="Markdown",
                                     reply_markup=get_main_keyboard())
            except Exception:
                await message.answer("⚠️ Could not reach your trusted contact.", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ No trusted contact set.", reply_markup=get_main_keyboard())


# ── Trusted Contact ───────────────────────────────────────────────────────────

@dp.message(F.text == "👤 Trusted Contact")
async def trusted_contact_handler(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    contacts = load_contacts()

    current = contacts.get(user_id)
    info = f"\nCurrent: *{current['name']}* (ID: `{current['telegram_id']}`)" if current else "\nNo trusted contact set yet."

    await message.answer(
        f"👤 *Trusted Contact*{info}\n\n"
        "To add or update, send the Telegram *user ID* and *name* in this format:\n"
        "`123456789 Anna`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Cancel")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ContactState.waiting_for_contact)

@dp.message(ContactState.waiting_for_contact, F.text == "❌ Cancel")
async def contact_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.", reply_markup=get_main_keyboard())

@dp.message(ContactState.waiting_for_contact)
async def contact_received(message: Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("❌ Invalid format. Please send: `123456789 Name`", parse_mode="Markdown")
        return

    contact_id, name = int(parts[0]), parts[1]
    user_id = str(message.from_user.id)

    contacts = load_contacts()
    contacts[user_id] = {"telegram_id": contact_id, "name": name}
    save_contacts(contacts)

    await message.answer(
        f"✅ Trusted contact saved: *{name}* (`{contact_id}`)\n\n"
        "⚠️ Make sure they have also started this bot so they can receive alerts.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    await state.clear()


# ── Safe Exit ─────────────────────────────────────────────────────────────────

@dp.message(F.text == "🚪 Safe Exit")
async def safe_exit_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚪 Goodbye. Stay safe.",
        reply_markup=ReplyKeyboardRemove()
    )


# ── Run ───────────────────────────────────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import logging
import json
import os
import time
import random
import asyncio
import requests
from database import ensure_connection
from datetime import datetime
from aiogram import Dispatcher, html
from aiogram.filters import CommandStart, CommandObject
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.markdown import hlink
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import FSInputFile
from ping3 import ping
from states import OrderFood

boter = 'anonimemessages_bot' # your bot


logging.basicConfig(level=logging.INFO)
def log_to_json(question_sender_id, question_receiver_id, question_text, answer_text):
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question_sender_id": question_sender_id,
        "question_receiver_id": question_receiver_id,
        "question_text": question_text,
        "answer_text": answer_text
    }

    today_date = datetime.now().strftime("%Y-%m-%d")
    log_file_path = f"{today_date}_logs.json"

    if not os.path.exists(log_file_path):
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            json.dump([], log_file, ensure_ascii=False)

    try:
        with open(log_file_path, 'r', encoding='utf-8') as log_file:
            logs = json.load(log_file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logs = []
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            json.dump(logs, log_file, ensure_ascii=False)


    logs.append(log_entry)

    with open(log_file_path, 'w', encoding='utf-8') as log_file:
        json.dump(logs, log_file, ensure_ascii=False, indent=4)
        
def register_handlers(dp: Dispatcher, conn, bot):
    @dp.message(CommandStart(deep_link=True))
    async def start(message: Message, command: CommandObject, state: FSMContext):
        args = command.args
        await message.reply(f'Ух-ты, какой(-ая) ты. Давай задавай вопрос быстрее!')
        await state.update_data(chat_id=args)
        await state.set_state(OrderFood.choosing_food_name)

    @dp.message(OrderFood.choosing_food_name)
    async def handle_question(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        username = message.from_user.username
        user_id = message.from_user.id
        chat_id = data.get('chat_id')
        question = message.text
        
        if question.startswith('/'):
            await message.reply(f"⚠️ <b>Нельзя вводить команды для вопросов.\nПерезадайте вопрос по ссылке: t.me/{boter}?start={message.chat.id}</b>", parse_mode='HTML')
            await state.clear()
        else:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                result = await cursor.fetchone()

                if username is None:
                        username = 'Unknown' 

                if result is None:
                    await cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
                await conn.commit()
                
            inline_kb_full = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="👉 Поделиться ссылкой", url=f"t.me/share/url?url=t.me/{boter}?start={user_id}"),
                    InlineKeyboardButton(text="👉 Спросить еще раз", url=f"t.me/{boter}?start={chat_id}")
                ]
            ])
            await message.answer(f"Вы задали вопрос пользователю.", reply_markup=inline_kb_full)

            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Ответить", callback_data=f"answer_{user_id}")],
                [InlineKeyboardButton(text="🫀 Узнай кто пишет", url=f"https://teletype.in/@naumov_glav/IJC3_mb6lnH")]
            ])


            async with conn.cursor() as cursor:
                await cursor.execute("SELECT vip FROM users WHERE user_id = %s", (chat_id,))
                vip_result = await cursor.fetchone()
                

            logging.info(f'Debug: Fetched VIP status = {vip_result}')

            vip = vip_result[0] if vip_result is not None else 0

            cat2 = FSInputFile("new.jpg")

            if vip == 1:
                cat = FSInputFile("new.jpg")
                await bot.send_message(chat_id=chat_id, text=f"<b>Вопрос: {question}\nОт пользователя: @{message.from_user.username} |  {message.from_user.full_name}\n\n\n </b>", reply_markup=keyboard, parse_mode = 'HTML')
                await bot.send_message(chat_id=chat_id, text=f"<b>Вас спросили: {question} </b>", reply_markup=keyboard, parse_mode = 'HTML')
            else:
                await bot.send_message(chat_id=chat_id, text =f"<b>Вас спросили: {question} </b>", reply_markup=keyboard, parse_mode = 'HTML')
                
            log_to_json(user_id, chat_id, question, "Not answered yet") 

            await state.clear()



    @dp.callback_query(lambda call: call.data.startswith("answer_"))
    async def process_callback_answer(callback_query: CallbackQuery, state: FSMContext):
        user_id = callback_query.data.split("_")[1]
        user_by_id = callback_query.from_user.id
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await callback_query.message.answer("Что вы хотите ответить?")
        await state.update_data(user_id=user_id, user_answer = user_by_id, full_name=callback_query.from_user.full_name)
        await state.set_state(OrderFood.answering_user)

    @dp.message(OrderFood.answering_user)
    async def answer_user(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get('user_id')
        user_by = data.get('user_answer')
        full_name = data.get('full_name')
        answer = message.text
        await message.reply(f"Вы ответили!")
        
        cat = FSInputFile("ask.jpeg")
        await bot.send_message(chat_id=user_id, text=f'Вам ответил пользователь: {full_name} | <b>ответ: {answer}</b>\n👉 Задайте новый вопрос этому же человеку: t.me/{boter}?start={user_by}')
                
        log_to_json(user_id, user_id, "Not logged", answer)  

        await state.clear()

    @dp.callback_query(lambda call: call.data.startswith("answers"))
    async def process_callback_answers(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await callback_query.message.answer("Что вы хотите ответить?")
        await state.set_state(OrderFood.answering_usere)

    @dp.message(OrderFood.answering_usere)
    async def answers_user(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        answer = message.text
        await message.reply(f"Вы отправили ответ {answer}")

        await state.clear()

    @dp.message(CommandStart())
    async def command_start_handler(message: Message) -> None:
        user_id = message.from_user.id
        username = message.from_user.username
        async with conn.cursor() as cursor:
            
            start = await ensure_connection(conn)
            print("Good command")
            await cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            result = await cursor.fetchone()

            if result is None:
                await cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
            await conn.commit()
            

        cat = FSInputFile("faq.png")
        inline_kb_full = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👉 Поделиться ссылкой", url=f"t.me/share/url?url=t.me/{boter}?start={user_id}")
            ],
            [
                InlineKeyboardButton(text="ℹ️ Гайд", url=f"https://teletype.in/@naumov_glav/N5QjJHV0iRO")
            ],
            [
                InlineKeyboardButton(text="📞 Поддержка", url=f"t.me/naumov_glav")
            ]
        ])

        await bot.send_message(
            user_id,
            text=(
                f"<b>Твоя ссылка для анонимных вопросов - <code> t.me/{boter}?start={user_id} </code> </b>\n\n"
                "<b>Разместите эту ссылку в описании своего профиля Telegram, TikTok, Instagram (stories), чтобы вам могли написать </b>\n\n"
            ),
            reply_markup=inline_kb_full, parse_mode='HTML'
        )

    @dp.message(Command("admin"))
    async def admin_handler(message: Message) -> None:
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (message.from_user.id,))
            result = await cursor.fetchone()
            

            key = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ | Рассылка", callback_data="rass"),
                        InlineKeyboardButton(text="💋 | Статистика", callback_data='users'),
                    ],
                    [
                        InlineKeyboardButton(text="😤 | Рассылка вопросом", callback_data='rass_vop'),
                        InlineKeyboardButton(text="😀 | Лог общений ", callback_data='logs'),
                    ],
                    [
                        InlineKeyboardButton(text="🤟 | VIP ", callback_data='vip'),
                        InlineKeyboardButton(text="😍 | UN-VIP ", callback_data='unvip'),
                    ],
                ]

            )
            if result and result[0] == 1:
                await bot.send_message(message.from_user.id, text="MENU-ADMIN. Выбери то, что тебе нужно", reply_markup=key)
            else:
                await bot.send_message(message.from_user.id, text="Ошибка: вы не администратор!")

    @dp.callback_query(lambda call: call.data.startswith("logs"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()
            

            if result and result[0] == 1:
                today_date = datetime.now().strftime("%Y-%m-%d")
                log_file_path = FSInputFile(f"{today_date}_logs.json")
                await bot.send_document(chat_id=callback_query.from_user.id, document=log_file_path, caption="Логи дня")
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()


    @dp.callback_query(lambda call: call.data.startswith("unvip"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()
            

            if result and result[0] == 1:
                await bot.send_message(callback_query.from_user.id, text="введите ID человека, у которого забрали VIP")
                await state.update_data(admin = callback_query.from_user.id)
                await state.set_state(OrderFood.admin_unvip)
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()

    @dp.message(OrderFood.admin_unvip)
    async def admin_text(message: Message, state: FSMContext) -> None:
        text = message.text
        data =  await state.get_data()
        admin = data.get("admin")
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT vip FROM users WHERE user_id = %s", (text,))
            user_data = await cursor.fetchone()

        if user_data:
            user_vip_status = user_data[0] 
            if user_vip_status == 1:
                try:
                    await bot.send_message(chat_id=text, text=f"У вас забрали VIP вип статус")
                    async with conn.cursor() as cursor2:
                        start = await ensure_connection(conn)
                        await cursor2.execute("UPDATE users SET vip = 0 WHERE user_id = %s", (text,))
                        await conn.commit()
                except TelegramForbiddenError:
                    print(f"User {text} has blocked the bot.")
            else: 
                await bot.send_message(admin, text="У этого пользователя уже нет VIP статуса!")
        else:
            await bot.send_message(admin, text="Такого пользователя нет в базе!")
        await state.clear()


    @dp.callback_query(lambda call: call.data.startswith("vip"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()
            

            if result and result[0] == 1:
                await bot.send_message(callback_query.from_user.id, text="введите ID человека, которого хотите сделать VIP")
                await state.update_data(admin = callback_query.from_user.id)
                await state.set_state(OrderFood.admin_vip)
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()

    @dp.message(OrderFood.admin_vip)
    async def admin_text(message: Message, state: FSMContext) -> None:
        text = message.text
        data =  await state.get_data()
        admin = data.get("admin")
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT vip FROM users WHERE user_id = %s", (text,))
            user_data = await cursor.fetchone()

        if user_data:
            user_vip_status = user_data[0] 
            if user_vip_status == 0:
                try:
                    await bot.send_message(chat_id=text, text=f"Вам выдали VIP-статус. Ознакомьтесь - https://teletype.in/@naumov_glav/IJC3_mb6lnH")
                    async with conn.cursor() as cursor2:
                        start = await ensure_connection(conn)
                        await cursor2.execute("UPDATE users SET vip = 1 WHERE user_id = %s", (text,))
                        await conn.commit()
                except TelegramForbiddenError:
                    print(f"User {text} has blocked the bot.")
            else: 
                await bot.send_message(admin, text="У этого пользователя уже есть VIP статуса!")
        else:
            await bot.send_message(admin, text="Такого пользователя нет в базе!")
        await state.clear()


    @dp.callback_query(lambda call: call.data.startswith("rass_vop"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()
            

            if result and result[0] == 1:
                await bot.send_message(callback_query.from_user.id, text="Введите текст для рассылки")
                await state.set_state(OrderFood.admin_text_vop)
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()



    @dp.message(OrderFood.admin_text_vop)
    async def admin_text(message: Message, state: FSMContext) -> None:
        text = message.text
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ответить", callback_data="answers")]
        ])

        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT user_id FROM users")
            users = await cursor.fetchall()

        for user in users:
            user_id = user[0]
            try:
                cat2 = FSInputFile('new.jpg')
                await bot.send_message(chat_id=user_id, text=f"Вопрос: {text}", reply_markup=keyboard)
            except Exception as e:
                if "chat not found" in str(e):
                    print(f"Chat not found for user ID: {user_id}. Skipping this user.")
                else:
                    print(f"An error occurred while sending message to user ID: {user_id}. Error: {e}")
            except TelegramForbiddenError:
                print(f"User {user_id} has blocked the bot.")

        await state.clear()

    @dp.callback_query(lambda call: call.data.startswith("users"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()

            if result and result[0] == 1:
                await cursor.execute("SELECT COUNT(*) FROM users")
                count = await cursor.fetchone()
                

                ip_address = 'www.google.com'
                response = ping(ip_address)
                print(response)
                if response is not None:
                    delay = int(response * 1000)
                    print(delay, " Delay ")
                await bot.send_message(callback_query.from_user.id, text=f"Всего пользователей: {count[0]}\nPing: {delay}")
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()

    @dp.callback_query(lambda call: call.data.startswith("rass"))
    async def rass_callback(callback_query: CallbackQuery, state: FSMContext):
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT admin FROM users WHERE user_id = %s", (callback_query.from_user.id,))
            result = await cursor.fetchone()
            

            if result and result[0] == 1:
                await bot.send_message(callback_query.from_user.id, text="Введите текст для рассылки")
                await state.set_state(OrderFood.admin_text)
            else:
                await bot.send_message(callback_query.from_user.id, text="Ошибка: вы не администратор!")
                await state.clear()

    @dp.message(OrderFood.admin_text)
    async def admin_text(message: Message, state: FSMContext) -> None:
        text = message.text

        async with conn.cursor() as cursor:
            start = await ensure_connection(conn)
            await cursor.execute("SELECT user_id FROM users")
            users = await cursor.fetchall()
            

        for user in users:
            user_id = user[0]
            try:
                await bot.send_message(chat_id=user_id, text=f"⚠️ Администратор отправил новое сообщение: \n\n{text}")
            except Exception as e:
                if "chat not found" in str(e):
                    print(f"Chat not found for user ID: {user_id}. Skipping this user.")
                else:
                    print(f"An error occurred while sending message to user ID: {user_id}. Error: {e}")
            except TelegramForbiddenError:
                print(f"User {user_id} has blocked the bot.")

        await state.clear()

    @dp.message(lambda message: not message.text.startswith("/"))
    async def handle_unknown_command(message: Message):
        await message.reply("⚠️ Команды не существует. Пожалуйста, воспользуйтесь /start")



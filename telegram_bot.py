import pandas as pd
import sqlite3
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
)
import logging

TG_TOKEN = "YOUR_TG_TOKEN"
df = pd.read_excel('df_for_survey_5.xlsx')

MODELS_COUNT = 7

conn = sqlite3.connect('survey.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS responses (
        user_id INTEGER,
        question_num INTEGER,
        cleaned_index INTEGER,
        gen_index INTEGER,
        gen_column TEXT,
        user_choice INTEGER,
        is_correct INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

QUESTION = range(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

GENDER, PHOTO, LOCATION, BIO = range(4)

async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton("Начать", callback_data='start_survey')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! \n\n"
        "🦾 Это бот для проведения опроса, являющегося частью дипломной работы "
        "<i>«Генерация текстов новостей в условиях информационного противоборства»</i> \n\n"
        f"🤖 Далее будет <b>{MODELS_COUNT} вопросов</b>, в каждом из которых нужно <b>выбрать новость, "
        "которая, по вашему мнению, сгенерирована нейросетью </b>\n\n"
        "💡 Заголовки новостей во всех примерах настоящие, генерировался лишь текст статьи",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    logger.info("User started a dialog")


async def start_survey(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    all_indices = list(range(len(df)))
    
    cleaned_indices = random.sample(all_indices, MODELS_COUNT)
    remaining = list(set(all_indices) - set(cleaned_indices))
    gen_indices = random.sample(remaining, MODELS_COUNT)
    
    gen_columns = [
        # 'gen_llama3_8b', 
        'gen_yagpt_8b', 
        'gen_rugpt_13b',
        'gen_tliteit_7b',
        'gen_llama3_8b_lora',
        'gen_mistral_7b_lora', 
    #    'gen_mistral_7b', 
        'gen_qwen_7b',
        'gen_qwen_7b_lora', 
    #    'gen_llama_8b', 
    #    'gen_llama_8b_instruct'
    ]
    assert len(gen_columns) == MODELS_COUNT

    context.user_data['survey'] = {
        'questions': list(zip(cleaned_indices, gen_indices, gen_columns)),
        'current_q': 0,
        'correct_answers': 0
    }
    
    await send_question(update, context)

    logger.info(f"User {user_id} started a started survey")

    return QUESTION

async def send_question(update: Update, context: CallbackContext) -> None:
    try:
        user_data = context.user_data['survey']
        q_num = user_data['current_q']
        cleaned_idx, gen_idx, gen_col = user_data['questions'][q_num]
        
        human_text = df.iloc[cleaned_idx]['real']
        ai_text = df.iloc[gen_idx][gen_col]
        options = [human_text, ai_text]
        random.shuffle(options)
        
        context.user_data['correct_answer'] = options.index(ai_text)
        
        keyboard = [
            [
                InlineKeyboardButton("🔵 НОВОСТЬ 1", callback_data='0'),
                InlineKeyboardButton("🟣 НОВОСТЬ 2", callback_data='1')
            ]
        ]

        op0 = options[0].strip() 
        op1 = options[1].strip()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Вопрос №{q_num + 1}: какая из новостей сгенерирована нейросетью? \n\n"
            f"🔵 <b>НОВОСТЬ 1:</b>\n\n{op0}\n\n🟣 <b>НОВОСТЬ 2:</b>\n\n{op1}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)


async def handle_answer(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    
    user_data = context.user_data['survey']
    q_num = user_data['current_q']
    cleaned_idx, gen_idx, gen_col = user_data['questions'][q_num]
    
    chosen = int(query.data)
    is_correct = chosen == context.user_data['correct_answer']
    
    cursor.execute('''
        INSERT INTO responses 
        (user_id, question_num, cleaned_index, gen_index, gen_column, user_choice, is_correct)
        VALUES (?,?,?,?,?,?,?)
    ''', (
        query.from_user.id,
        q_num + 1,
        cleaned_idx,
        gen_idx,
        gen_col,
        chosen + 1,
        is_correct
    ))
    conn.commit()

    if is_correct:
        user_data['correct_answers'] += 1
    
    # Edit message to add result and remove buttons
    result_symbol = "✅ Верный ответ" if is_correct else "❌ Неверный ответ"
    original_text = query.message.text
    new_text = f"{original_text}\n\n{result_symbol}"
    
    await query.edit_message_text(
        text=new_text,
        reply_markup=None,
        parse_mode="HTML",
    )

    user_data['current_q'] += 1
    
    if user_data['current_q'] < MODELS_COUNT:
        await send_question(update, context)
        return QUESTION
    else:
        total = user_data['correct_answers']
        keyboard = [[InlineKeyboardButton("Начать", callback_data='start_survey')]]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🥰 Большое спасибо за ответы!\n\n🎯 Правильных ответов: {total}/{MODELS_COUNT} \n\n🎲 Хотите пройти еще раз?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"user {user_id} finished a survey")
        return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(TG_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_survey, pattern='^start_survey$')],
        states={
            QUESTION: [CallbackQueryHandler(handle_answer)]
        },
        fallbacks=[],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

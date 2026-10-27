"""Bot texts in English and Russian.

The language is picked from the user's Telegram app language. Add a new language by
adding an entry to TEXTS with the same keys as "en".
"""

from __future__ import annotations

DEFAULT_LANG = "en"

# Telegram language codes that get Russian replies.
RUSSIAN_SPEAKING = frozenset({"ru", "be", "kk", "ky"})

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "start": (
            "👋 Hi, <b>{name}</b>!\n\n"
            "Send me a link to a video and I'll send the file right here.\n\n"
            "<b>Works with</b>\n"
            "▶️ YouTube and Shorts\n"
            "🎵 TikTok\n"
            "📸 Instagram Reels\n"
            "🌐 X, Vimeo, Reddit and 1000+ other sites\n\n"
            "<b>How</b>: tap <i>Share → Copy link</i> in the app, paste it here, "
            "then choose a quality or 🎵 MP3. Short clips come right away."
        ),
        "help": (
            "<b>How to use</b>\n"
            "1. Send a video link.\n"
            "2. Choose a quality or 🎵 MP3.\n"
            "3. Wait, and I'll send you the file.\n\n"
            "Short clips with only one or two qualities are sent right away, with a 🎵 MP3 button under them.\n"
            "Max file size: <b>{limit}</b>. Playlists and live streams aren't supported.\n\n"
            "Changed your mind? Tap ✖️ Cancel under the progress bar."
        ),
        "cmd_start": "Start the bot",
        "cmd_help": "How to use",
        "cmd_users": "Who can use the bot",
        "not_allowed": "⛔ This is a private bot.\nYour Telegram ID: <code>{user_id}</code>",
        "not_allowed_alert": "⛔ This is a private bot.",
        "access_requested": (
            "👋 This is a private bot. I've asked the owner to let you in.\n"
            "You'll get a message here as soon as they say yes."
        ),
        "access_pending": "⏳ Still waiting for the owner to let you in.",
        "access_granted": "🎉 You're in! Send me a link to a video to start.",
        "access_request": "🔔 <b>Access request</b>\n👤 {name}\n🆔 <code>{user_id}</code>",
        "approve_button": "✅ Let in",
        "deny_button": "❌ Decline",
        "approved": "✅ Let in",
        "denied": "❌ Declined",
        "users_title": "👥 <b>Who can use the bot</b>",
        "users_from_env": "From .env (change them there): {ids}",
        "users_none": (
            "Nobody added from the chat yet. Share the bot's link: when someone opens it, you'll get a request here."
        ),
        "users_hint": "Tap a name to remove that person.",
        "user_removed": "Removed {name}.",
        "no_link": "Send me a link to a video 🔗",
        "bad_link": "⚠️ I can't use this link.",
        "fetching": "🔎 Looking up the video…",
        "choose": "🎬 <b>{title}</b>\n{details}\n\nChoose quality:",
        "audio_button": "🎵 Audio (MP3)",
        "best_button": "⬇️ Best quality",
        "nothing_fits": "😔 Even the smallest version of this video is larger than {limit}.",
        "downloading": "⬇️ Downloading <b>{quality}</b>…",
        "queued": "⏳ <b>{quality}</b>: waiting in line, another download is running…",
        "processing": "⚙️ <b>{quality}</b>: almost done…",
        "uploading": "⬆️ Sending to Telegram…",
        "cancel_button": "✖️ Cancel",
        "cancelling": "Cancelling…",
        "cancel_too_late": "Nothing to cancel.",
        "cancelled": "✖️ Download cancelled.",
        "expired": "⌛ This request has expired. Send the link again.",
        "busy": "⏳ Wait until your current download finishes.",
        "too_large": "📦 The file is {size}, larger than the {limit} limit. Choose a lower quality.",
        "playlist": "📃 Playlists aren't supported. Send a link to a single video.",
        "live": "🔴 Live streams aren't supported.",
        "error_unsupported": "❌ I can't download from this link. Make sure it's correct and public.",
        "error_restricted": (
            "🔒 This video is private, age-restricted or requires login. "
            "The bot owner can add cookies to fix this (see README)."
        ),
        "error_blocked": (
            "🤖 The site is blocking this server. The bot owner can add cookies or a proxy to fix this (see README)."
        ),
        "error_generic": "❌ Something went wrong. Try again later or choose another quality.",
    },
    "ru": {
        "start": (
            "👋 Привет, <b>{name}</b>!\n\n"
            "Отправь мне ссылку на видео, и я пришлю файл прямо сюда.\n\n"
            "<b>Что умею скачивать</b>\n"
            "▶️ YouTube и Shorts\n"
            "🎵 TikTok\n"
            "📸 Instagram Reels\n"
            "🌐 X, Vimeo, Reddit и 1000+ других сайтов\n\n"
            "<b>Как</b>: нажми <i>Поделиться → Копировать ссылку</i> в приложении, вставь её сюда "
            "и выбери качество или 🎵 MP3. Короткие ролики присылаю сразу."
        ),
        "help": (
            "<b>Как пользоваться</b>\n"
            "1. Отправь ссылку на видео.\n"
            "2. Выбери качество или 🎵 MP3.\n"
            "3. Подожди — я пришлю файл.\n\n"
            "Короткие ролики с одним-двумя вариантами качества присылаю сразу, с кнопкой 🎵 MP3 под ними.\n"
            "Максимальный размер файла: <b>{limit}</b>. Плейлисты и прямые эфиры не поддерживаются.\n\n"
            "Передумал? Нажми ✖️ Отмена под полоской загрузки."
        ),
        "cmd_start": "Запустить бота",
        "cmd_help": "Как пользоваться",
        "cmd_users": "Кто может пользоваться ботом",
        "not_allowed": "⛔ Это приватный бот.\nТвой Telegram ID: <code>{user_id}</code>",
        "not_allowed_alert": "⛔ Это приватный бот.",
        "access_requested": (
            "👋 Это приватный бот. Я попросил владельца пустить тебя.\nКак только он ответит, тебе придёт сообщение."
        ),
        "access_pending": "⏳ Всё ещё ждём ответа владельца.",
        "access_granted": "🎉 Готово, доступ есть! Отправь ссылку на видео.",
        "access_request": "🔔 <b>Запрос доступа</b>\n👤 {name}\n🆔 <code>{user_id}</code>",
        "approve_button": "✅ Пустить",
        "deny_button": "❌ Отказать",
        "approved": "✅ Доступ открыт",
        "denied": "❌ Отказано",
        "users_title": "👥 <b>Кто может пользоваться ботом</b>",
        "users_from_env": "Из .env (меняются там): {ids}",
        "users_none": (
            "Из чата пока никого не добавили. Поделись ссылкой на бота: когда кто-то его откроет, сюда придёт запрос."
        ),
        "users_hint": "Нажми на имя, чтобы убрать человека.",
        "user_removed": "{name} больше не может пользоваться ботом.",
        "no_link": "Отправь мне ссылку на видео 🔗",
        "bad_link": "⚠️ Эту ссылку нельзя использовать.",
        "fetching": "🔎 Ищу видео…",
        "choose": "🎬 <b>{title}</b>\n{details}\n\nВыбери качество:",
        "audio_button": "🎵 Аудио (MP3)",
        "best_button": "⬇️ Лучшее качество",
        "nothing_fits": "😔 Даже самая маленькая версия этого видео больше {limit}.",
        "downloading": "⬇️ Скачиваю <b>{quality}</b>…",
        "queued": "⏳ <b>{quality}</b>: жду своей очереди, сейчас идёт другая загрузка…",
        "processing": "⚙️ <b>{quality}</b>: почти готово…",
        "uploading": "⬆️ Отправляю в Telegram…",
        "cancel_button": "✖️ Отмена",
        "cancelling": "Отменяю…",
        "cancel_too_late": "Нечего отменять.",
        "cancelled": "✖️ Загрузка отменена.",
        "expired": "⌛ Запрос устарел. Отправь ссылку ещё раз.",
        "busy": "⏳ Дождись окончания текущей загрузки.",
        "too_large": "📦 Файл весит {size} — это больше лимита {limit}. Выбери качество пониже.",
        "playlist": "📃 Плейлисты не поддерживаются. Отправь ссылку на одно видео.",
        "live": "🔴 Прямые эфиры не поддерживаются.",
        "error_unsupported": "❌ Не получается скачать по этой ссылке. Проверь, что она верная и публичная.",
        "error_restricted": (
            "🔒 Видео приватное, с возрастным ограничением или требует входа в аккаунт. "
            "Владелец бота может добавить cookies (см. README)."
        ),
        "error_blocked": (
            "🤖 Сайт блокирует этот сервер. Владелец бота может добавить cookies или прокси (см. README)."
        ),
        "error_generic": "❌ Что-то пошло не так. Попробуй позже или выбери другое качество.",
    },
}


def resolve_lang(language_code: str | None) -> str:
    """Map a Telegram language code (e.g. 'ru', 'en-US') to a supported language."""
    if not language_code:
        return DEFAULT_LANG
    base = language_code.split("-")[0].lower()
    return "ru" if base in RUSSIAN_SPEAKING else DEFAULT_LANG


def t(lang: str, key: str, **kwargs: object) -> str:
    """Return the text for `key` in `lang`, falling back to English."""
    texts = TEXTS.get(lang, TEXTS[DEFAULT_LANG])
    template = texts.get(key) or TEXTS[DEFAULT_LANG][key]
    return template.format(**kwargs) if kwargs else template

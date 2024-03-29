import logging
import os
import requests
import sys
import telegram
import time
from dotenv import load_dotenv
from http import HTTPStatus
from telegram.error import TelegramError

load_dotenv()

PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: dict = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: dict = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)


def check_tokens() -> bool:
    """Проверка доступности переменных окружения."""
    variables: list = [PRACTICUM_TOKEN,
                       TELEGRAM_TOKEN,
                       TELEGRAM_CHAT_ID]
    return all(variables)


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправка сообщения в чат."""
    try:
        logger.info('Отправка сообщения в чат')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение отправлено')
    except TelegramError as error:
        logger.error(f'Ошибка отправки сообщения: {error}')


def get_api_answer(timestamp: dict) -> dict:
    """Отправка запроса к эндпоинту."""
    try:
        homeworks = requests.get(ENDPOINT, headers=HEADERS, params=timestamp)
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к эндпоинту: {error}')

    if homeworks.status_code != HTTPStatus.OK:
        raise ConnectionError(f'Эндпоинт {ENDPOINT} недоступен. '
                              f'Код ответа API: {homeworks.status_code}')
    return homeworks.json()


def check_response(response: dict) -> dict:
    """Проверка ответа API."""
    if type(response) is not dict:
        raise TypeError(f'Некорректный тип данных: {type(response)}')
    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ "homeworks"')
    if type(response['homeworks']) is not list:
        raise TypeError(
            f'Некорректный тип данных {type(response["homeworks"])}'
        )

    if not response['homeworks']:
        return {}
    return response['homeworks'][0]


def parse_status(homework: dict) -> str:
    """Получение информации об обновлении статуса проверки."""
    if homework:
        if 'homework_name' not in homework:
            raise KeyError('Отсутствует ключ "homework_name"')
        if 'status' not in homework:
            raise KeyError('Отсутствует ключ "status"')
        if not homework['status']:
            raise ValueError('Статус проверки работы пуст')
        if homework['status'] not in HOMEWORK_VERDICTS:
            raise KeyError(
                'Статус проверки не соответствует ожидаемым вариантам'
            )

        homework_name = homework['homework_name']
        status = homework['status']
        verdict = HOMEWORK_VERDICTS[status]
        message = ('Изменился статус проверки работы '
                   f'"{homework_name}". {verdict}')
    else:
        message = 'Статус проверки работы не изменился'

    logger.debug(message)
    return message


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют обязательные переменные окружения! '
                        'Работа программы принудительно завершена')
        sys.exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.info('Бот запущен!')
    timestamp = {'from_date': int(time.time())}
    previous_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)

            current_date = response.get('current_date')
            timestamp = {'from_date': current_date}

            homework = check_response(response)
            message = parse_status(homework)
            if message == previous_message:
                continue
            send_message(bot, message)
            previous_message = message

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message == previous_message:
                continue
            send_message(bot, message)
            previous_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()

import threading
import time
import datetime
import telebot

from enum import IntEnum, StrEnum
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.database_utils import DatabaseAPI
from game.game import Game, TurnResult, GameResultCode, TurnResultCode


class _Status(IntEnum):
    IS_NOW_CHAT = 0
    IS_NOW_AWAITING_TOKEN = 1
    IS_NOW_GAME = 2


# В данном случае используется StrEnum так как параметр callback_data класса InlineKeyboardMarkup требует
# строчный тип данных входного значения
class _CallData(StrEnum):
    START = "start"
    JOIN = "join"
    TURN = "turn"


def _log(message: str):
    date = datetime.datetime.today()
    print(f"{str(date)}: {message}")


def _check_players(timestamps: {int, int}, statuses: {int, _Status}, games: [Game], reset_time: int):
    while True:
        time.sleep(reset_time)

        if len(timestamps) > 0 and len(statuses) > 0:
            time_five_minute_ago = time.time() - reset_time

            for key, value in list(timestamps.items()):
                if time_five_minute_ago > value:
                    for i in range(len(games)):
                        if games[i].is_player_in_game(key):
                            del games[i]

                    del timestamps[key], statuses[key]
                    _log(f"Пользователь {key} удалён из оперативной памяти")


class BotClient:
    def __init__(self, bot_token: str, database_conn_kwargs: {str: str}, reset_time: int):
        """
        :param bot_token: уникальный токен Telegram-бота
        """

        self._chats_statuses = {}
        """
        _chats_statuses: {player_id: int, status: _Status}
        Словарь содержащий в себе статусы всех пользователей
        
        player_id:
            id игрока
        status:
            _Status.IS_NOW_CHAT - еще не идёт игра или поиск сессии
            _Status.IS_NOW_AWAITING_TOKEN - ожидается ввод токена для присоеденения к существующей сессии
            _Status.IS_NOW_GAME - в данный момент идёт игра
        """

        self._timestamps = {}
        """
        _timestamps: {player_id: int, timestamp: int}
        Словарь содержащий в себе время последней активности каждого пользователя

        player_id:
            id игрока
        timestamp:
            время в секундах
        """

        self._games = []
        """
        _games: {game: Game}
        Список всех игр идущих на данный момент
        """

        self.bot = telebot.TeleBot(bot_token, parse_mode=None)
        """
        Текущий экземпляр класса TeleBot содержащий API для управления Telegram-ботом
        """

        self.database_api = DatabaseAPI(database_conn_kwargs)
        """
        Текущий экземпляр класса DatabaseAPI содержащий API для запросов к БД
        """

        # Запускает новый поток который ассинхронно каждые несколько секунд проверяет пользователей (период задается в
        # файле start.bat)
        #
        # Удаляет данные о пользователе из оперативной памяти, если пользователь не делал никаких действий больше чем
        # заданный период времени (это необходимо чтоб уменьшить расходы оперативной памяти, но не использовать запросы
        # к БД слишком часто)
        update_users_thread = threading.Thread(
            target=_check_players,
            args=(self._timestamps, self._chats_statuses, self._games, reset_time)
        )
        update_users_thread.start()

        # Изменяет время последней активности пользователя. Если пользователь не загружен из БД - загружает, если
        # это новый пользователь - также добавляет его в БД
        #
        # Загрузка данных пользователя из БД делается для того чтобы, не приходилось каждый раз при смене статуса
        # пользователя открывать соединение с БД и изменять или загружать данные, а работать с данными в оперативной
        # памяти
        def _update_timestamp(player_id: int):
            if player_id in self._chats_statuses.keys() and player_id in self._timestamps.keys():
                self._timestamps[player_id] = time.time()
            else:
                is_user_in_bd_query = self.database_api.is_user_in_bd(player_id)

                if is_user_in_bd_query.success:
                    if is_user_in_bd_query.data:
                        self._chats_statuses[player_id] = _Status.IS_NOW_CHAT
                    else:
                        user_append_query = self.database_api.append_user(player_id)

                        if user_append_query.success:
                            self._chats_statuses[player_id] = _Status.IS_NOW_CHAT
                            _log(f"Новый пользователь {player_id}")
                        else:
                            self.bot.send_message(player_id, text="Ошибка")

                    self._timestamps[player_id] = time.time()
                    _log(f"Пользователь {player_id} загружен из БД")
                else:
                    self.bot.send_message(player_id, text="Ошибка")

        # Обрабатывает сообщение если отправивший его пользователь не начал поиск сессии или игру и просто общается с
        # ботом или если это новый пользователь
        @self.bot.message_handler(
            func=lambda message:
                message.text[0] != '/' and
                (
                    message.from_user.id not in self._chats_statuses.keys()
                    or
                    self._chats_statuses[message.from_user.id] == _Status.IS_NOW_CHAT
                )
        )
        def chat_message_handler(message: Message):
            player_id = message.from_user.id
            _update_timestamp(player_id)

            self.bot.reply_to(message, text="Привет, это бот для игры в крестики-нолики. Введите /start чтобы начать"
                                            "игру")

        # Обрабатывает сообщение если отправивший его пользователь должен ввести токен подключения к существующей сессии
        @self.bot.message_handler(
            func=lambda message:
                message.text[0] != '/' and
                self._chats_statuses[message.from_user.id] == _Status.IS_NOW_AWAITING_TOKEN
        )
        def token_message_handler(message):
            player_id = message.from_user.id
            token = message.text
            _update_timestamp(player_id)

            if message.text != 'нет':
                game = self._find_game_by_session_token(token)

                if game is not None:
                    is_join_success = self._join_to_game(game, player_id)

                    if is_join_success:
                        start_matrix = game.start_game()

                        markup = self._matrix_to_markup(start_matrix)
                        message_matrix = self._matrix_to_emojis(start_matrix)

                        turn_player_id = game.turn_now_player.id
                        wait_player_id = game.awaiting_player.id

                        self.bot.send_message(turn_player_id, "Сессия найдена, вы играете за \"X\".\nВаш ход:")
                        self.bot.send_message(turn_player_id, message_matrix, reply_markup=markup)

                        self.bot.send_message(wait_player_id, "Сессия найдена, вы играете за \"О\".\nОжидайте ход "
                                                              "другого игрока...")
                        self.bot.send_message(wait_player_id, message_matrix)

                        self._chats_statuses[turn_player_id] = _Status.IS_NOW_GAME
                        self._chats_statuses[wait_player_id] = _Status.IS_NOW_GAME

                        _log(f"Сессия {token}. Игроки - 2")
                else:
                    self.bot.reply_to(message, "Не найдена сессия")
                    self._chats_statuses[player_id] = _Status.IS_NOW_CHAT
            else:
                self._chats_statuses[player_id] = _Status.IS_NOW_CHAT

        # Обрабатывает сообщение если отправивший его пользователь сейчас в игре
        @self.bot.message_handler(
            func=lambda message:
                message.text[0] != '/' and
                self._chats_statuses[message.from_user.id] == _Status.IS_NOW_GAME
        )
        def chat_message_handler_while_game(message):
            player_id = message.from_user.id
            _update_timestamp(player_id)

        # В следующих обработчиках проверяется лишь первый элемент callback_data так как он содержит информацию об
        # нажатой кнопке, остальные элементы будут содержать координаты хода игрока

        # Обрабатывает нажатие на кнопку "СТАРТ"
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.START)
        def start_session_callback(call):
            player_id = call.from_user.id

            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                token = self._create_new_game(player_id)
                self.bot.send_message(player_id, text=f"Токен вашей сессии: {token}")
                _log(f"Начата новая сессия {token}")
                _log(f"Сессия {token}. Игроки - 1")
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас начать новую сессию")

        # Обрабатывает нажатие на кнопку "ПРИСОЕДИНИТЬСЯ"
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.JOIN)
        def join_session_callback(call):
            player_id = call.from_user.id

            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                self.bot.send_message(player_id, text="Введите токен сессии к которой хотите присоедениться или 'нет' "
                                                      "если хотите выйти:")
                self._chats_statuses[player_id] = _Status.IS_NOW_AWAITING_TOKEN
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас присоедениться к сессии")

        # Обрабатывает нажатие на кнопку хода
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.TURN)
        def game_turn_callback(call):
            player_id = call.from_user.id

            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_GAME:
                game: Game = self._find_game_by_player_id(player_id)

                # После каждого хода экземпляр класса Game самостоятельно меняет роли игроков
                turn_player_id = game.turn_now_player.id
                wait_player_id = game.awaiting_player.id

                if player_id == turn_player_id:
                    turn_res = self._game_turn(game, player_id, call.data)

                    if turn_res.is_turn_success:
                        message_matrix = self._matrix_to_emojis(turn_res.matrix)

                        match turn_res.game_result_code:
                            case GameResultCode.GAME_CONTINUE:
                                markup = self._matrix_to_markup(turn_res.matrix)

                                self.bot.send_message(turn_player_id, f"Результат вашего хода:\n{message_matrix}")
                                self.bot.send_message(turn_player_id, "Ожидайте ход другого игрока...")

                                self.bot.send_message(wait_player_id, "Ваш ход:")
                                self.bot.send_message(wait_player_id, message_matrix, reply_markup=markup)

                            case GameResultCode.NO_ONE_WIN:
                                self.bot.send_message(turn_player_id, f"Ничья:\n{message_matrix}")
                                self.bot.send_message(wait_player_id, f"Ничья:\n{message_matrix}")

                                turn_player_query = self.database_api.increment_draws(turn_player_id)
                                wait_player_query = self.database_api.increment_draws(wait_player_id)

                                if turn_player_query.success and wait_player_query.success:
                                    _log(f"Изменены данные пользователя {turn_player_id} в БД ")
                                    _log(f"Изменены данные пользователя {wait_player_id} в БД ")
                                else:
                                    self.bot.send_message(turn_player_id, "Ошибка. Данные не сохраненны")
                                    self.bot.send_message(wait_player_id, "Ошибка. Данные не сохраненны")

                                self._end_game(game)

                            case GameResultCode.PLAYER_WIN:
                                self.bot.send_message(turn_player_id, f"Результат вашего хода:\n{message_matrix}")
                                self.bot.send_message(turn_player_id, "Вы выиграли")

                                self.bot.send_message(wait_player_id, f"Ход другого игрока:\n{message_matrix}")
                                self.bot.send_message(wait_player_id, "Вы проиграли")

                                turn_player_query = self.database_api.increment_wins(turn_player_id)
                                wait_player_query = self.database_api.increment_loses(wait_player_id)

                                if turn_player_query.success and wait_player_query.success:
                                    _log(f"Изменены данные пользователя {turn_player_id} в БД ")
                                    _log(f"Изменены данные пользователя {wait_player_id} в БД ")
                                else:
                                    self.bot.send_message(turn_player_id, "Ошибка. Данные не сохраненны")
                                    self.bot.send_message(wait_player_id, "Ошибка. Данные не сохраненны")

                                self._end_game(game)
                    else:
                        match turn_res.turn_result_code:
                            case TurnResultCode.INCORRECT_TURN:
                                self.bot.send_message(turn_player_id, "Неправильный ход")
                            case TurnResultCode.NO_PLAYER:
                                self.bot.send_message(turn_player_id, "Не найден игрок")
                            case TurnResultCode.NO_SESSION:
                                self.bot.send_message(turn_player_id, "Не найдена сессия")
                else:
                    self.bot.send_message(wait_player_id, "Ожидайте ваш ход")

        @self.bot.message_handler(commands=["start"])
        def command_leaders_message_handler(message):
            player_id = message.from_user.id
            _update_timestamp(player_id)

            start_button = InlineKeyboardButton("СТАРТ", callback_data=_CallData.START)
            join_button = InlineKeyboardButton("ПРИСОЕДИНИТЬСЯ", callback_data=_CallData.JOIN)

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(start_button, join_button)

            self.bot.reply_to(message, text="Нажмите СТАРТ чтобы начать новую игру, или ПРИСОЕДИНИТЬСЯ чтобы "
                                            "присоединиться к существующей", reply_markup=markup)

        @self.bot.message_handler(commands=["leaders"])
        def command_leaders_message_handler(message):
            player_id = message.from_user.id
            get_leaders_query = self.database_api.get_leaders()
            _update_timestamp(player_id)

            if get_leaders_query.success:
                data = get_leaders_query.data
                out_str = ""

                if len(data) > 0 and data is not None:
                    out_str += "Вот результаты лучших игроков\n\n"
                    place = 1

                    for i in data:
                        win_rate = 'недостаточно данных' if i[1] is None else f"{round(100*i[1], 1)}%"
                        out_str += f"{place}. {i[0]} - {win_rate}\n"
                        place += 1
                else:
                    out_str = "Нет данных о лучших игроках"

                self.bot.send_message(player_id, text=out_str)
            else:
                self.bot.send_message(player_id, text="Ошибка")

        @self.bot.message_handler(commands=["score"])
        def command_score_message_handler(message):
            player_id = message.from_user.id
            get_score_query = self.database_api.get_user_score(player_id)
            _update_timestamp(player_id)

            if get_score_query.success:
                if get_score_query.data is not None:
                    data = get_score_query.data

                    wins = data[0]
                    loses = data[1]
                    draws = data[2]
                    win_rate = "недостаточно данных" if data[3] is None else f"{round(data[3], 1)}%"
                    nick = "нет" if data[4] is None else data[4]

                    name = player_id if data[4] is None else data[4]

                    out_str = \
                        f"""Вот результаты игрока {name}:
                            
                        Винрейт - {win_rate}

                        Победы - {wins}
                        Поражения - {loses}
                        Ничьи - {draws}
                                                        
                        id: {player_id}
                        Никнейм: {nick}
                        """
                else:
                    out_str = "Нет данных об игроке"

                self.bot.send_message(player_id, text=out_str)
            else:
                self.bot.send_message(player_id, text="Ошибка")

        @self.bot.message_handler(commands=["nick"])
        def command_nick_message_handler(message):
            player_id = message.from_user.id
            _update_timestamp(player_id)

            if len(message.text.split(' ')) == 2:
                nick = message.text.split(' ')[1]
                set_nick_query = self.database_api.set_nickname(player_id, nick)

                if set_nick_query.success:
                    self.bot.send_message(player_id, text=f"Теперь вас зовут {nick}")
                else:
                    self.bot.send_message(player_id, text="Ошибка")
            else:
                self.bot.send_message(player_id, text="Ошибка ввода. Введите данные в формате - \"/nick никнейм\". "
                                                      "Никнейм не должен содержать пробелы.")

    def _create_new_game(self, player_id: int) -> str:
        """
        Создает новую игру с одним игроком
        :param player_id: id игрока
        :return: Токен сессии
        """

        time_based_token = str(int(time.time()))

        game = Game()
        game.start_new_session(player_id, time_based_token)

        self._games.append(game)

        return time_based_token

    @staticmethod
    def _join_to_game(game: Game, player_id: int) -> bool:
        """
        Присоединяет игрока к существующей игре
        :param player_id: id игрока
        :return: True - если попытка присоединения прошла удачно
        """

        is_join_to_session = game.join_to_session(player_id)
        start_matrix = game.start_game()

        if is_join_to_session and start_matrix is not None:
            return True
        else:
            return False

    @staticmethod
    def _game_turn(game: Game, player_id: int, raw_turn: str) -> TurnResult:
        """
        :param game: игра в которой будет сделан ход
        :param player_id: id игрока
        :param raw_turn: строка с информацией о ходе
        :return: Экземпляр класса TurnResult с информацией о результате хода
        """

        turn = [int(i) for i in raw_turn.split(' ')[1:]]
        turn_data = game.make_turn(player_id, turn[0], turn[1])

        return turn_data

    @staticmethod
    def _matrix_to_markup(matrix: [[str]]) -> InlineKeyboardMarkup:
        """
        Преобразование 3х3 матрицы из строк в интерактивную клавиатуру
        :param matrix: двумерный список из строк показывающий текущее состояние игры
        :returns: Экземпляр класса InlineKeyBoardMarkup используемый для создания интерактивной клавиатуры в сообщении
        """

        markup = telebot.types.InlineKeyboardMarkup(row_width=3)

        cell_1_1 = InlineKeyboardButton(matrix[0][0], callback_data=f'{_CallData.TURN} 0 0')
        cell_1_2 = InlineKeyboardButton(matrix[0][1], callback_data=f'{_CallData.TURN} 0 1')
        cell_1_3 = InlineKeyboardButton(matrix[0][2], callback_data=f'{_CallData.TURN} 0 2')
        markup.row(cell_1_1, cell_1_2, cell_1_3)

        cell_2_1 = InlineKeyboardButton(matrix[1][0], callback_data=f'{_CallData.TURN} 1 0')
        cell_2_2 = InlineKeyboardButton(matrix[1][1], callback_data=f'{_CallData.TURN} 1 1')
        cell_2_3 = InlineKeyboardButton(matrix[1][2], callback_data=f'{_CallData.TURN} 1 2')
        markup.row(cell_2_1, cell_2_2, cell_2_3)

        cell_3_1 = InlineKeyboardButton(matrix[2][0], callback_data=f'{_CallData.TURN} 2 0')
        cell_3_2 = InlineKeyboardButton(matrix[2][1], callback_data=f'{_CallData.TURN} 2 1')
        cell_3_3 = InlineKeyboardButton(matrix[2][2], callback_data=f'{_CallData.TURN} 2 2')
        markup.row(cell_3_1, cell_3_2, cell_3_3)

        return markup

    @staticmethod
    def _matrix_to_emojis(matrix: [[str]]) -> str:
        """
        Преобразование 3х3 матрицы из строк в строку сообщения
        :param matrix: двумерный список из строк показывающий текущее состояние игры
        """

        out_str = ""

        for row in matrix:
            row_str = ""

            for cell in row:
                if cell == ' ':
                    row_str += "⬜️"
                elif cell == 'O':
                    row_str += "⭕️"
                elif cell == "X":
                    row_str += "❌"

            row_str += "\n"
            out_str += row_str

        return out_str

    def _find_game_by_player_id(self, player_id: int) -> Game:
        """
        Поиск игры по id участника
        :param player_id: id игрока
        :return: None - если игра не найдена, экземпляр класса Game - если игра найдена
        """

        game = None

        for g in self._games:
            for p in g.players:
                if player_id == p.id:
                    game = g

        return game

    def _find_game_by_session_token(self, session_token: str) -> Game:
        """
        Поиск игры по токену игровой сессии
        :param session_token: токен сессии
        :return: None - если игра не найдена, экземпляр класса Game - если игра найдена
        """

        game = None

        for g in self._games:
            if session_token == g.session_token:
                game = g

        return game

    def _end_game(self, game: Game):
        """
        Заканчивает игровую сессию
        :param game: игра которую требуется завершить
        """

        session_token = game.session_token
        players = game.players

        for pl in players:
            self._chats_statuses[pl.id] = _Status.IS_NOW_CHAT

        for i in range(len(self._games)):
            if self._games[i].session_token == session_token:
                del self._games[i]

    def start(self):
        """
        Запуск бота
        """
        _log("Старт бота")
        self.bot.infinity_polling()

import threading
import time
import datetime
import telebot

from enum import IntEnum, StrEnum
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.database_utils import DatabaseAPI
from game.game import Game, TurnResult, GameResultCode, TurnResultCode, GameAI
from keras.models import Sequential


class _Status(IntEnum):
    IS_NOW_CHAT = 0
    IS_NOW_AWAITING_TOKEN = 1
    IS_NOW_GAME = 2
    IS_NOW_AWAITING_PLAYER = 3
    IS_NOW_AI_GAME = 4


# В данном случае используется StrEnum так как параметр callback_data класса InlineKeyboardMarkup требует
# строчный тип данных входного значения
class _CallData(StrEnum):
    BUTTON_AI = "ai"
    BUTTON_START = "start"
    BUTTON_JOIN = "join"
    SESSION_JOIN = "session"
    TURN = "turn"
    TURN_AI = "turn_ai"
    RESET = "reset"


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
    def __init__(self, bot_token: str, database_conn_kwargs: {str: str}, reset_time: int, model: Sequential | None):
        """
        :param bot_token: уникальный токен Telegram-бота
        :param database_conn_kwargs: словарь с аргументами для соединения с БД
        :param reset_time: время после которого пользователь будет удален из оперативной памяти (не из БД)
        :param model: модель для игры против AI, или None - если не подразумевается режим против бота
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

        self._ai_games = []
        """
        _ai_games: {ai_game: GameAI}
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

        self.model: Sequential | None = model
        """
        Текущий экземпляр класса Sequential представляющий модель глубокой нейронной сети для предсказания 
        самого оптимального хода при игре против AI
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
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.BUTTON_START)
        def button_start_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            nick_query = self.database_api.get_nickname(player_id)
            nickname = None

            if nick_query.success:
                nickname = nick_query.data

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                token = self._create_new_game(player_id)
                button = InlineKeyboardMarkup()
                button.add(InlineKeyboardButton(text="Отмена", callback_data=_CallData.RESET))

                if nickname is None:
                    self.bot.send_message(player_id,
                                          text=f"Теперь в списке игр будет ваш id: {player_id}. Чтобы установить себе "
                                               f"никнейм вместо id воспользуйтесь командой /nick 'ваш ник'",
                                          reply_markup=button
                                          )
                else:
                    self.bot.send_message(player_id,
                                          text=f"Теперь в списке игр будет ваш ник: {nickname}",
                                          reply_markup=button
                                          )

                self._chats_statuses[player_id] = _Status.IS_NOW_AWAITING_PLAYER
                _log(f"Начата новая сессия {token}")
                _log(f"Сессия {token}. Игроки - 1")
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас начать новую сессию")

        # Обрабатывает нажатие на кнопку "ПРИСОЕДИНИТЬСЯ"
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.BUTTON_JOIN)
        def button_join_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                non_fulled_games = [i for i in self._games if len(i.players) == 1]

                if len(non_fulled_games) == 0:
                    self.bot.send_message(player_id, text="Сейчас никто не ищет противников. Попробуйте начать свою "
                                                          "игру или сыграйте против AI")
                else:
                    self.bot.send_message(player_id,
                                          text="Список всех доступных игр, нажмите чтобы присоединиться:",
                                          reply_markup=self._games_to_markup()
                                          )
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас присоедениться к сессии")

        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.SESSION_JOIN)
        def session_join_session_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                token = call.data.split(' ')[1]
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
                        self.bot.send_message(player_id, "Не получилось присоедениться к игре")
                else:
                    self.bot.send_message(player_id, "Не найдена сессия, возможно первый игрок отменил игру, или место "
                                                     "уже занято")
            else:
                self.bot.send_message(player_id, "Вы не можете сейчас присоедениться к игре")

        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.RESET)
        def reset_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_GAME:
                for i in range(len(self._games)):
                    game = self._games[i]
                    awaiting_player_id = game.awaiting_player.id
                    turn_now_player_id = game.turn_now_player.id

                    if player_id == awaiting_player_id:
                        self.bot.send_message(awaiting_player_id, text="Вы сдались")
                        self.bot.send_message(turn_now_player_id, text="Ваш противник сдался")
                        self._chats_statuses[turn_now_player_id] = _Status.IS_NOW_CHAT

                    if player_id == turn_now_player_id:
                        self.bot.send_message(turn_now_player_id, text="Вы сдались")
                        self.bot.send_message(awaiting_player_id, text="Ваш противник сдался")
                        self._chats_statuses[awaiting_player_id] = _Status.IS_NOW_CHAT

                    if player_id == awaiting_player_id or player_id == turn_now_player_id:
                        del self._games[i]

            if self._chats_statuses[player_id] == _Status.IS_NOW_AI_GAME:
                for i in range(len(self._ai_games)):
                    ai_game = self._ai_games[i]

                    if player_id == ai_game.player.id:
                        self.bot.send_message(player_id, text="Вы сдались")

                        del self._ai_games[i]

            if self._chats_statuses[player_id] == _Status.IS_NOW_AWAITING_PLAYER:
                for i in range(len(self._games)):
                    game = self._games[i]
                    player = game.players[0]

                    if player_id == player.id:
                        self.bot.send_message(player_id, text="Отмена игры")

                        del self._games[i]

            self._chats_statuses[player_id] = _Status.IS_NOW_CHAT

        # Обрабатывает нажатие на кнопку хода
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.TURN)
        def game_turn_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_GAME:
                game: Game = self._find_game_by_player_id(player_id)

                turn_player_id = player_id
                wait_player_id = [pl for pl in game.players if pl.id != player_id][0]

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
            else:
                self.bot.send_message(player_id, "Вы не можете сейчас ходить")

        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.BUTTON_AI)
        def button_ai_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                self._create_new_ai_game(player_id)
                self._chats_statuses[player_id] = _Status.IS_NOW_AI_GAME

                ai_games = [i for i in self._ai_games if i.player.id == player_id]

                if len(ai_games) > 0:
                    ai_game = ai_games[0]
                    matrix = ai_game.matrix

                    markup = self._ai_matrix_to_markup(matrix)
                    message_matrix = self._matrix_to_emojis(matrix)

                    self.bot.send_message(player_id, "Игра началась, вы играете за \"X\".\nВаш ход:")
                    self.bot.send_message(player_id, message_matrix, reply_markup=markup)

                    self._chats_statuses[player_id] = _Status.IS_NOW_AI_GAME

                    _log(f"Игрок {player_id} начал сессию против AI")
                else:
                    self.bot.send_message(player_id, text="Ошибка начала игры")
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас начать игру")

        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.TURN_AI)
        def ai_game_turn_callback(call):
            player_id = call.from_user.id
            _update_timestamp(player_id)

            if self._chats_statuses[player_id] == _Status.IS_NOW_AI_GAME:
                ai_games = [i for i in self._ai_games if i.player.id == player_id]

                if len(ai_games) > 0:
                    ai_game = ai_games[0]
                    turn_res = self._ai_game_turn(ai_game, call.data)

                    if turn_res.is_turn_success:
                        message_matrix = self._matrix_to_emojis(turn_res.matrix)

                        match turn_res.game_result_code:
                            case GameResultCode.GAME_CONTINUE:
                                markup = self._ai_matrix_to_markup(turn_res.matrix)

                                self.bot.send_message(player_id, "Теперь ваш ход:")
                                self.bot.send_message(player_id, message_matrix, reply_markup=markup)

                            case GameResultCode.NO_ONE_WIN:
                                self.bot.send_message(player_id, f"Ничья:\n{message_matrix}")

                                self._end_ai_game(ai_game)

                            case GameResultCode.PLAYER_WIN:
                                self.bot.send_message(player_id, f"Результат вашего хода:\n{message_matrix}")
                                self.bot.send_message(player_id, "Вы выиграли")

                                self._end_ai_game(ai_game)
                            case GameResultCode.AI_WIN:
                                self.bot.send_message(player_id, f"Результат хода бота:\n{message_matrix}")
                                self.bot.send_message(player_id, "Вы прогирали")

                                self._end_ai_game(ai_game)
                    else:
                        if turn_res.turn_result_code == TurnResultCode.INCORRECT_TURN:
                            self.bot.send_message(player_id, "Неправильный ход")
                else:
                    self.bot.send_message(player_id, "Ошибка хода")
            else:
                self.bot.send_message(player_id, "Вы не можете сейчас ходить")

        @self.bot.message_handler(commands=["start"])
        def command_leaders_message_handler(message):
            player_id = message.from_user.id
            _update_timestamp(player_id)

            markup = InlineKeyboardMarkup(row_width=1)

            if self.model is not None:
                markup.row(InlineKeyboardButton("ИГРА С БОТОМ", callback_data=_CallData.BUTTON_AI))

            markup.row(InlineKeyboardButton("СТАРТ", callback_data=_CallData.BUTTON_START))
            markup.row(InlineKeyboardButton("ПРИСОЕДИНИТЬСЯ", callback_data=_CallData.BUTTON_JOIN))

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
                        win_rate = 'недостаточно данных' if i[1] is None else f"{round(100 * i[1], 1)}%"
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

    def _create_new_ai_game(self, player_id: int):
        """
        Создает новую игру с одним игроком
        :param player_id: id игрока
        :return: Токен сессии
        """

        ai_game = GameAI(model=self.model)
        ai_game.start_new_session(player_id)

        self._ai_games.append(ai_game)

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
    def _ai_game_turn(ai_game: GameAI, raw_turn: str) -> TurnResult:
        """
        :param ai_game: игра в которой будет сделан ход
        :param raw_turn: строка с информацией о ходе
        :return: Экземпляр класса TurnResult с информацией о результате хода
        """

        turn = [int(i) for i in raw_turn.split(' ')[1:]]
        turn_data = ai_game.make_turn(turn[0], turn[1])

        return turn_data

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

    def _games_to_markup(self) -> InlineKeyboardMarkup:
        not_fulled_games = [i for i in self._games if len(i.players) == 1]
        awaiting_players_ids = [i.players[0].id for i in not_fulled_games]
        awaiting_players_data = self.database_api.get_nicknames(awaiting_players_ids).data

        awaiting_players_tokens = [i.session_token for i in not_fulled_games]
        awaiting_players_names = []

        for player_id, player_data in zip(awaiting_players_ids, awaiting_players_data):
            if player_data is None:
                awaiting_players_names.append(str(player_id))
            else:
                awaiting_players_names.append(player_data)

        markup = telebot.types.InlineKeyboardMarkup(row_width=1)

        for i in range(len(not_fulled_games)):
            cell = InlineKeyboardButton(
                text=f"Присоеденится к {awaiting_players_names[i]}",
                callback_data=f"{_CallData.SESSION_JOIN} {awaiting_players_tokens[i]}"
            )

            markup.row(cell)

        return markup

    @staticmethod
    def _ai_matrix_to_markup(matrix: [[str]]) -> InlineKeyboardMarkup:
        """
        Преобразование 3х3 матрицы из строк в интерактивную клавиатуру
        :param matrix: двумерный список из строк показывающий текущее состояние игры
        :returns: Экземпляр класса InlineKeyBoardMarkup используемый для создания интерактивной клавиатуры в сообщении
        """

        markup = telebot.types.InlineKeyboardMarkup(row_width=3)

        cell_1_1 = InlineKeyboardButton(matrix[0][0], callback_data=f'{_CallData.TURN_AI} 0 0')
        cell_1_2 = InlineKeyboardButton(matrix[0][1], callback_data=f'{_CallData.TURN_AI} 0 1')
        cell_1_3 = InlineKeyboardButton(matrix[0][2], callback_data=f'{_CallData.TURN_AI} 0 2')
        markup.row(cell_1_1, cell_1_2, cell_1_3)

        cell_2_1 = InlineKeyboardButton(matrix[1][0], callback_data=f'{_CallData.TURN_AI} 1 0')
        cell_2_2 = InlineKeyboardButton(matrix[1][1], callback_data=f'{_CallData.TURN_AI} 1 1')
        cell_2_3 = InlineKeyboardButton(matrix[1][2], callback_data=f'{_CallData.TURN_AI} 1 2')
        markup.row(cell_2_1, cell_2_2, cell_2_3)

        cell_3_1 = InlineKeyboardButton(matrix[2][0], callback_data=f'{_CallData.TURN_AI} 2 0')
        cell_3_2 = InlineKeyboardButton(matrix[2][1], callback_data=f'{_CallData.TURN_AI} 2 1')
        cell_3_3 = InlineKeyboardButton(matrix[2][2], callback_data=f'{_CallData.TURN_AI} 2 2')
        markup.row(cell_3_1, cell_3_2, cell_3_3)

        markup.row(InlineKeyboardButton(text="Отмена", callback_data=_CallData.RESET))

        return markup

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

        markup.row(InlineKeyboardButton(text="Отмена", callback_data=_CallData.RESET))

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
            if session_token == g.session_token and len(g.players) == 1:
                game = g

        return game

    def _end_ai_game(self, ai_game: GameAI):
        """
        Заканчивает игровую сессию
        :param ai_game: игра которую требуется завершить
        """

        player = ai_game.player
        self._chats_statuses[player.id] = _Status.IS_NOW_CHAT

        for i in range(len(self._ai_games)):
            if self._ai_games[i].player.id == player.id:
                del self._ai_games[i]

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

import dataclasses
import datetime

from mysql.connector import connect, Error, MySQLConnection, CMySQLConnection
from mysql.connector.pooling import PooledMySQLConnection


@dataclasses.dataclass
class DatabaseOperationResult:
    """
    Данные о запросе к БД:
    succes: bool - успешен запрос или нет
    data: int or [int] or {int: (int, int, int)} or (int, int, int) or None - если запрос к БД подразумевает возвращение
    данных и запрос был успешен, то содержит возвращаемые данные, в противном случае - None
    """
    success: bool
    data: any


def _log(error: Error, func_name: str):
    date = datetime.datetime.today()
    print(f"{str(date)}: (запрос к БД послал ошибку) {func_name} => {error.msg}")


class DatabaseAPI:
    def __init__(self, db_connect_kwargs):
        self.db_connect_kwargs = db_connect_kwargs

        # Создаем таблицу с данными пользователя если её нет
        with connect(**self.db_connect_kwargs) as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        """
                            CREATE TABLE IF NOT EXISTS users(
                                id INT PRIMARY KEY NOT NULL UNIQUE,
                                wins INT UNSIGNED,
                                loses INT UNSIGNED,
                                draws INT UNSIGNED,
                                win_rate FLOAT,
                                nickname TEXT
                            )
                        """
                    )
                except Error as e:
                    _log(e, "DatabaseAPI.__init__")

    # Данный декоратор автоматически вставляет в первый аргумент функции класс позволяющий работать с БД для того чтобы
    # не приходилось прописывать это каждый раз при добавлении нового API для работы с БД
    @staticmethod
    def _database_operation(func):
        match func.__name__:
            case "get_users_ids" | "get_users_scores" | "get_leaders":
                def wrapper(self):
                    with connect(**self.db_connect_kwargs) as connection:
                        try:
                            data = func(self, connection)
                            connection.close()

                            return data
                        except Error as e:
                            _log(e, func.__name__)

                            return DatabaseOperationResult(False, None)

                out_func = wrapper
            case "set_nickname":
                def wrapper(self, user_id: int, nickname: str):
                    with connect(**self.db_connect_kwargs) as connection:
                        try:
                            data = func(self, connection, user_id, nickname)
                            connection.close()

                            return data
                        except Error as e:
                            _log(e, func.__name__)

                            return DatabaseOperationResult(False, None)

                out_func = wrapper
            case _:
                def wrapper(self, user_id: int):
                    with connect(**self.db_connect_kwargs) as connection:
                        try:
                            data = func(self, connection, user_id)
                            connection.close()

                            return data
                        except Error as e:
                            _log(e, func.__name__)

                            return DatabaseOperationResult(False, None)

                out_func = wrapper

        return out_func

    @_database_operation
    def get_users_ids(self,
                      conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None
                      ) -> DatabaseOperationResult:
        """
        Возвращает id всех пользователей в БД в виде экземпляра класса DatabaseOperationResult где в случае успеха
        data это список всех id, в противном случае - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :return: DatabaseOperationResult(success: bool, data: [int] | None)
        """
        out_list = []

        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT id FROM users")
                result = cursor.fetchall()

                for row in result:
                    out_list.append(int(row[0]))

                return DatabaseOperationResult(True, out_list)
            except Error as e:
                _log(e, "get_users_ids")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def get_users_scores(self,
                         conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None
                         ) -> DatabaseOperationResult:
        """
        Возвращает данные о всех пользователей в БД в виде экземпляра класса DatabaseOperationResult где в случае успеха
        data это словарь где ключ - id пользователя, значение - картеж из 4 чисел и строки: количество побед, количество
        поражений, количество ничьих, винрейт, никнейм; в противном случае - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :return: DatabaseOperationResult(success: bool, data: {int: (int, int, int, int, str)} | None)
        """
        out_dict = {}

        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT * FROM users")
                result = cursor.fetchall()

                for row in result:
                    out_dict[row[0]] = (row[1], row[2], row[3], row[4], row[5])

                return DatabaseOperationResult(True, out_dict)
            except Error as e:
                _log(e, "get_users_scores")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def get_user_score(self,
                       conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                       user_id: int) -> DatabaseOperationResult:
        """
        Возвращает данные о пользователе в БД по его id в виде экземпляра класса DatabaseOperationResult где в случае
        успеха data это картеж из 4 чисел и строки: количество побед, количество поражений, количество ничьих, винрейт,
        никнейм; в противном случае - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: (int, int, int, int, str) | None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
                rows = cursor.fetchall()

                if len(rows) == 1:
                    result = rows[0]

                    return DatabaseOperationResult(True, (result[1], result[2], result[3], result[4], result[5]))
                else:
                    return DatabaseOperationResult(True, None)
            except Error as e:
                _log(e, "get_user_score")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def is_user_in_bd(self,
                      conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                      user_id: int) -> DatabaseOperationResult:
        """
        Возвращает данные о наличии пользователя в БД по его id в виде экземпляра класса DatabaseOperationResult где,
        в случае успеха data это True если пользователь есть в БД и False - если нет, в противном случае - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: bool | None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(f"SELECT id FROM users WHERE id = {user_id} LIMIT 1")
                rows = cursor.fetchall()

                if len(rows) == 1:
                    return DatabaseOperationResult(True, True)
                else:
                    return DatabaseOperationResult(True, False)
            except Error as e:
                _log(e, "is_user_in_bd")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def append_user(self,
                    conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                    user_id: int) -> DatabaseOperationResult:
        """
        Добавляет нового пользователя в БД

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(f"INSERT INTO users VALUE ({user_id}, 0, 0, 0, null, null)")
                conn.commit()

                return DatabaseOperationResult(True, None)
            except Error as e:
                conn.rollback()
                _log(e, "append_user")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def increment_wins(self,
                       conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                       user_id: int) -> DatabaseOperationResult:
        """
        Увеличивает количество побед пользователя в БД на 1 по его id

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT id, wins, loses, draws FROM users "
                               f"WHERE id = {user_id}")
                row = cursor.fetchall()[0]
                row = (row[0], row[1] + 1, row[2], row[3])

                cursor.execute(
                    "UPDATE users "
                    f"SET id={row[0]}, wins={row[1]}, loses={row[2]}, draws={row[3]}, win_rate={row[1]/(row[1]+row[2])}"
                    f"WHERE id = {user_id}"
                )
                conn.commit()

                return DatabaseOperationResult(True, None)
            except Error as e:
                conn.rollback()
                _log(e, "increment_wins")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def increment_loses(self,
                        conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                        user_id: int) -> DatabaseOperationResult:
        """
        Увеличивает количество поражений пользователя в БД на 1 по его id

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT id, wins, loses, draws FROM users "
                               f"WHERE id = {user_id}")
                row = cursor.fetchall()[0]
                row = (row[0], row[1], row[2] + 1, row[3])

                cursor.execute(
                    "UPDATE users "
                    f"SET id={row[0]}, wins={row[1]}, loses={row[2]}, draws={row[3]}, win_rate={row[1]/(row[1]+row[2])}"
                    f"WHERE id = {user_id}"
                )
                conn.commit()

                return DatabaseOperationResult(True, None)
            except Error as e:
                conn.rollback()
                _log(e, "increment_loses")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def increment_draws(self,
                        conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                        user_id: int) -> DatabaseOperationResult:
        """
        Увеличивает количество ничьих пользователя в БД на 1 по его id

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT id, wins, loses, draws FROM users "
                               f"WHERE id = {user_id}")
                row = cursor.fetchall()[0]
                row = (row[0], row[1], row[2], row[3] + 1)

                cursor.execute(
                    "UPDATE users "
                    f"SET id={row[0]}, wins={row[1]}, loses={row[2]}, draws={row[3]} "
                    f"WHERE id = {user_id}"
                )
                conn.commit()

                return DatabaseOperationResult(True, None)
            except Error as e:
                conn.rollback()
                _log(e, "increment_draws")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def get_nickname(self,
                     conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                     user_id: int) -> DatabaseOperationResult:
        """
        Возвращает ник пользователя в БД по его id в виде экземпляра класса DatabaseOperationResult, где в случае если
        такой пользователь есть в БД, и запрос был завершен без ошибок, data это строка содержащая ник, иначе - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :return: DatabaseOperationResult(success: bool, data: str | None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(f"SELECT nickname FROM users WHERE id = {user_id}")
                nickname = cursor.fetchall()

                if len(nickname) == 1:
                    return DatabaseOperationResult(True, nickname[0][0])
                else:
                    return DatabaseOperationResult(True, None)
            except Error as e:
                _log(e, "get_nickname")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def set_nickname(self,
                     conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                     user_id: int,
                     user_nickname: str
                     ) -> DatabaseOperationResult:
        """
        Устанавливает пользователю с нужным id новый ник

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :arg user_id: id пользователя
        :arg user_nickname: ник пользователя
        :return: DatabaseOperationResult(success: bool, data: None)
        """
        with conn.cursor() as cursor:
            try:
                var = f"UPDATE users SET nickname='{user_nickname}' WHERE id={user_id}"
                cursor.execute(var)

                conn.commit()

                return DatabaseOperationResult(True, None)
            except Error as e:
                conn.rollback()
                _log(e, "set_nickname")

                return DatabaseOperationResult(False, None)

    @_database_operation
    def get_leaders(self,
                    conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None
                    ) -> DatabaseOperationResult:
        """
        Возвращает список игроков с самым большим винрейтом в виде экземпляра класса DatabaseOperationResult, где в
        случае если запрос был завершен без ошибок, data это список из до 5 картежей где первый элемент это id или ник
        игрока (если есть), а второй - винрейт, иначе - None

        :arg conn: подключение к БД, автоматически заполняется декоратором
        :return: DatabaseOperationResult(success: bool, data: [(str, int)] | None)
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(f"SELECT id, nickname, win_rate FROM users ORDER BY win_rate DESC LIMIT 5")
                rows = cursor.fetchall()
                out_list = []

                for row in rows:
                    if row[1] is not None:
                        out_list.append((row[1], row[2]))
                    else:
                        out_list.append((str(row[0]), row[2]))

                return DatabaseOperationResult(True, out_list)
            except Error as e:
                _log(e, "get_leaders")

                return DatabaseOperationResult(False, None)

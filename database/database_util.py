import dataclasses

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
    data: int or [int] or {int: (int, int, int)} or (int, int, int) or None


# Данный декоратор автоматически вставляет в первый аргумент функции класс позволяющий работать с БД для того чтобы не
# приходилось прописывать это каждый раз при добавлении нового API для работы с БД
def _database_operation(func):
    if func.__name__ in ["get_users_ids", "get_users_scores"]:
        def wrapper():
            try:
                with connect(host="localhost", user="root", password="0968", database="data") as connection:
                    data = func(connection)
                    connection.close()

                    return data
            except Error as e:
                print(e)
                return DatabaseOperationResult(False, None)

        out_func = wrapper
    else:
        def wrapper(user_id: int):
            try:
                with connect(host="localhost", user="root", password="0968", database="data") as connection:
                    data = func(connection, user_id)
                    connection.close()

                    return data
            except Error as e:
                print(e)
                return DatabaseOperationResult(False, None)

        out_func = wrapper

    return out_func


@_database_operation
def get_users_ids(conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None) -> DatabaseOperationResult:
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
            print(e)

            return DatabaseOperationResult(False, None)


@_database_operation
def get_users_scores(
        conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None) -> DatabaseOperationResult:
    """
    Возвращает данные о всех пользователей в БД в виде экземпляра класса DatabaseOperationResult где в случае успеха
    data это словарь где ключ - id пользователя, значение - картеж из трёх чисел: количество побед, количество
    поражений, количество ничьих; в противном случае - None

    :arg conn: подключение к БД, автоматически заполняется декоратором
    :return: DatabaseOperationResult(success: bool, data: {int: (int, int, int)} | None)
    """
    out_dict = {}

    with conn.cursor() as cursor:
        try:
            cursor.execute("SELECT * FROM users")
            result = cursor.fetchall()

            for row in result:
                out_dict[row[0]] = (row[1], row[2], row[3])

            return DatabaseOperationResult(True, out_dict)
        except Error as e:
            print(e)

            return DatabaseOperationResult(False, None)


@_database_operation
def get_user_score(
        conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
        user_id: int) -> DatabaseOperationResult:
    """
    Возвращает данные о пользователе в БД по его id в виде экземпляра класса DatabaseOperationResult где в случае успеха
    data это картеж из трёх чисел: количество побед, количество поражений, количество ничьих; в противном случае - None

    :arg conn: подключение к БД, автоматически заполняется декоратором
    :arg user_id: id пользователя
    :return: DatabaseOperationResult(success: bool, data: (int, int, int) | None)
    """
    with conn.cursor() as cursor:
        try:
            cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
            result = cursor.fetchall()[0]

            return DatabaseOperationResult(True, (result[1], result[2], result[3]))
        except Error as e:
            print(e)

            return DatabaseOperationResult(False, None)


@_database_operation
def append_user(conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
                user_id: int) -> DatabaseOperationResult:
    """
    Добавляет нового пользователя в БД

    :arg conn: подключение к БД, автоматически заполняется декоратором
    :arg user_id: id пользователя
    :return: DatabaseOperationResult(success: bool, data: None)
    """
    with conn.cursor() as cursor:
        try:
            cursor.execute(f"INSERT INTO users VALUE ({user_id}, 0, 0, 0)")
            conn.commit()

            return DatabaseOperationResult(True, None)
        except Error as e:
            conn.rollback()

            print(e)
            return DatabaseOperationResult(False, None)


@_database_operation
def increment_wins(conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
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

            cursor.execute("UPDATE users "
                           f"SET id={row[0]}, wins={row[1] + 1}, loses={row[2]}, draws={row[3]} "
                           f"WHERE id = {user_id}")
            conn.commit()

            return DatabaseOperationResult(True, None)
        except Error as e:
            conn.rollback()

            print(e)
            return DatabaseOperationResult(False, None)


@_database_operation
def increment_loses(conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
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

            cursor.execute("UPDATE users "
                           f"SET id={row[0]}, wins={row[1]}, loses={row[2] + 1}, draws={row[3]} "
                           f"WHERE id = {user_id}")
            conn.commit()

            return DatabaseOperationResult(True, None)
        except Error as e:
            conn.rollback()

            print(e)
            return DatabaseOperationResult(False, None)


@_database_operation
def increment_draws(conn: PooledMySQLConnection | MySQLConnection | CMySQLConnection | None,
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

            cursor.execute("UPDATE users "
                           f"SET id={row[0]}, wins={row[1]}, loses={row[2]}, draws={row[3] + 1} "
                           f"WHERE id = {user_id}")
            conn.commit()

            return DatabaseOperationResult(True, None)
        except Error as e:
            conn.rollback()

            print(e)
            return DatabaseOperationResult(False, None)

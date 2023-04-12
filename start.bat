@SET TOKEN=6028879461:AAEge0mqpgq-zzMfyKj7NEao8LP0gD9XMU4
:: Задает токен бота
@SET /a RESET_TIME=300
:: Задает время бездействия пользователя после которого его удаляют из оперативной памяти (не из БД)
@SET /a USE_GAME_AI=1
:: Задает нужно ли загружать модель для игры в крестики-нолики против AI (1 - True, 0 - False)
@SET DATABASE_NAME=data
:: Задает название используемой БД
@SET DATABASE_USER=root
:: Задает имя пользоваетеля для соединения с БД
@SET DATABASE_PASSWORD=0968
:: Задает пароль для соединения с БД (да, писать его в .bat файле небезопасно, но мне лень его вводить каждый раз)

python main.py %TOKEN% %RESET_TIME% %USE_GAME_AI% %DATABASE_NAME% %DATABASE_USER% %DATABASE_PASSWORD%

pause

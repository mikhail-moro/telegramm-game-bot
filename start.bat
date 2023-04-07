@SET TOKEN=6028879461:AAEge0mqpgq-zzMfyKj7NEao8LP0gD9XMU4
:: Задает токен бота
@SET /a RESET_TIME=300
:: Задает время бездействия пользователя после которого его удаляют из оперативной памяти (не из БД)
@SET DATABASE_NAME=data
:: Задает название используемой БД
@SET DATABASE_USER=root
:: Задает имя пользоваетеля для соединения с БД
@SET DATABASE_PASSWORD=0968
:: Задает пароль для соединения с БД (да, писать его в .bat файле небезопасно, но мне лень его вводить каждый раз)

python main.py %TOKEN% %RESET_TIME% %DATABASE_NAME% %DATABASE_USER% %DATABASE_PASSWORD%

pause

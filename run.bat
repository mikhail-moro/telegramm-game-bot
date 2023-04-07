@SET TOKEN=6028879461:AAEge0mqpgq-zzMfyKj7NEao8LP0gD9XMU4
:: Задает токен бота
@SET /a RESET_TIME=300
:: Задает время бездействия пользователя после которого его удаляют из оперативной памяти (не из БД)

python main.py %TOKEN% %RESET_TIME%

pause

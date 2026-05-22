from chat_backend.chat_db import set_user_online, get_online_users

def mark_join(username):
    set_user_online(username, 1)

def mark_leave(username):
    set_user_online(username, 0)

def online_list():
    return get_online_users()